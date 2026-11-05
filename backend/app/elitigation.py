"""eLitigation adapter: SG Courts judgments from www.elitigation.sg/gd.

Two decoupled phases so downloading never needs the vector store:

  fetch  — walks the year-by-year listing (10 rows a page; no server-side
           court filter), keeps Supreme Court citations, and downloads each
           judgment page into a raw archive (data/raw/elitigation/<year>/
           <slug>.html) with an append-only manifest. One connection, an
           optional pause (ELITIGATION_DELAY_SECONDS, default 0), exponential
           backoff on 429/5xx, and resumable: files already on disk are
           skipped, and completed past-year listings are reused.
  index  — parses archived pages not yet in the corpus, embeds them, adds their
           citation edges, then reruns the treatment pass. Runs in the API
           server process (POST /api/admin/index-judgments) so the UI stays up,
           or from the CLI when the server is stopped (embedded Qdrant is
           single-process).

CLI:
  python -m app.elitigation fetch [--from-year 2000] [--to-year 2026] [--limit N]
  python -m app.elitigation index [--limit N]
  python -m app.elitigation status
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from bs4 import BeautifulSoup

from app.config import Settings, get_settings
from app.ingest.judgment_parser import SLUG_COURT_CODES, parse_elitigation_judgment

log = logging.getLogger(__name__)

BASE_URL = "https://www.elitigation.sg"
LISTING_PATH = "/gd/Home/Index"
JUDGMENT_PATH = "/gd/s/"
PAGE_SIZE = 10  # the site ignores larger PageSize values

# spec scope: Court of Appeal, Appellate Division, General Division, SICC
SUPREME_COURTS = ("SGCA", "SGCA(I)", "SGHC(A)", "SGHC", "SGHC(I)")

_SLUG_RX = re.compile(r"^(\d{4})_([A-Z]+)_(\d+)$")
_TOTAL_RX = re.compile(r"Total Judgment\(s\) Found\s*:\s*(\d+)")
_ISO_RX = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass
class ListingEntry:
    slug: str
    citation: str
    court_code: str
    year: int
    title: str = ""
    decision_date: str | None = None
    case_number: str = ""
    catchwords: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{BASE_URL}{JUDGMENT_PATH}{self.slug}"


def slug_to_citation(slug: str) -> tuple[str, str, int] | None:
    """'2026_SGHCA_26' -> ('[2026] SGHC(A) 26', 'SGHC(A)', 2026)."""
    m = _SLUG_RX.match(slug)
    if not m:
        return None
    year, code, num = int(m.group(1)), m.group(2), int(m.group(3))
    code = SLUG_COURT_CODES.get(code, code)
    return f"[{year}] {code} {num}", code, year


def parse_listing(html: str) -> tuple[list[ListingEntry], int | None]:
    """One listing page -> its rows and the reported total for the query."""
    soup = BeautifulSoup(html, "lxml")
    m = _TOTAL_RX.search(soup.get_text(" "))
    total = int(m.group(1)) if m else None
    entries: list[ListingEntry] = []
    for link in soup.find_all("a", href=re.compile(r"^/gd/s/")):
        slug = link["href"].rsplit("/", 1)[-1]
        parsed = slug_to_citation(slug)
        if not parsed:
            continue
        citation, code, year = parsed
        card = link.find_parent(class_="gd") or link.parent
        dd = card.find("a", class_="decision-date-link") if card else None
        iso = _ISO_RX.search(dd.get("data-searchparam", "")) if dd else None
        cn = card.find("a", class_="case-num-link") if card else None
        cws = card.find_all("a", class_="gd-cw") if card else []
        entries.append(ListingEntry(
            slug=slug, citation=citation, court_code=code, year=year,
            title=" ".join(link.get_text(" ").split()),
            decision_date=iso.group(1) if iso else None,
            case_number=" ".join(cn.get_text(" ").split()).strip(" |") if cn else "",
            catchwords=[" ".join(a.get_text(" ").split()).strip("[] ") for a in cws],
        ))
    return entries, total


def listing_params(year: int | str, page: int) -> dict[str, Any]:
    return {
        "Filter": "SUPCT", "YearOfDecision": str(year), "SortBy": "DateOfDecision",
        "CurrentPage": page, "SortAscending": "False", "PageSize": 0,
        "Verbose": "False", "SearchQueryTime": 0, "SearchTotalHits": 0,
        "SearchMode": "True", "SpanMultiplePages": "False",
    }


# ------------------------------------------------------------------ raw archive

class RawArchive:
    """data/raw/elitigation: <year>/<slug>.html, listings/<year>.json, manifest.jsonl."""

    def __init__(self, root: Path):
        self.root = root
        (root / "listings").mkdir(parents=True, exist_ok=True)

    @property
    def marker(self) -> Path:
        """Written by a fetch run that walked every requested year to the end."""
        return self.root / "fetch_complete.json"

    def page_path(self, entry: ListingEntry) -> Path:
        return self.root / str(entry.year) / f"{entry.slug}.html"

    def has(self, entry: ListingEntry) -> bool:
        p = self.page_path(entry)
        return p.exists() and p.stat().st_size > 0

    def save_page(self, entry: ListingEntry, html: str) -> None:
        p = self.page_path(entry)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(html, encoding="utf-8")
        tmp.replace(p)  # atomic: a killed run never leaves a half-written page
        record = asdict(entry) | {"fetched_at": datetime.now(timezone.utc).isoformat()}
        with (self.root / "manifest.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def manifest(self) -> list[dict]:
        """Latest record per slug, in fetch order."""
        path = self.root / "manifest.jsonl"
        if not path.exists():
            return []
        latest: dict[str, dict] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a run killed mid-write leaves at most one bad line
                latest[rec["slug"]] = rec
        return list(latest.values())

    def load_listing(self, year: int) -> dict | None:
        p = self.root / "listings" / f"{year}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def save_listing(self, year: int, entries: list[ListingEntry], total: int | None,
                     complete: bool) -> None:
        p = self.root / "listings" / f"{year}.json"
        p.write_text(json.dumps({
            "year": year, "total": total, "complete": complete,
            "walked_at": datetime.now(timezone.utc).isoformat(),
            "entries": [asdict(e) for e in entries]}))


# ------------------------------------------------------------------ fetcher

class ELitigationFetcher:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None,
                 sleep: Callable[[float], Any] = asyncio.sleep):
        self.s = settings
        self.archive = RawArchive(settings.data_dir / "raw" / "elitigation")
        self._client = client
        self._sleep = sleep
        self.stats = {"listing_pages": 0, "fetched": 0, "skipped_existing": 0,
                      "out_of_scope": 0, "errors": 0}

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=BASE_URL, timeout=60.0, follow_redirects=True,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            headers={"User-Agent": "sg-law-rag/0.1 (non-commercial legal-information "
                                   "research assistant; polite single-connection crawler)"})

    async def _get(self, client: httpx.AsyncClient, url: str,
                   params: dict | None = None) -> str:
        """GET with exponential backoff on network errors, 429 and 5xx."""
        pause = self.s.elitigation_delay_seconds
        delay = max(pause, 1.0)  # backoff base even when the pause is 0
        for attempt in range(6):
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}",
                                                request=resp.request, response=resp)
                resp.raise_for_status()
                if pause > 0:
                    await self._sleep(pause)
                return resp.text
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500 and status != 429:
                    raise
                delay = min(delay * 2, self.s.crawl_max_backoff_seconds)
                log.warning("GET %s failed (%s); retry %d in %.0fs", url, exc, attempt + 1, delay)
                await self._sleep(delay)
        raise RuntimeError(f"giving up on {url}")

    async def walk_year(self, client: httpx.AsyncClient, year: int) -> list[ListingEntry]:
        cached = self.archive.load_listing(year)
        if cached and cached.get("complete") and year < date.today().year:
            return [ListingEntry(**e) for e in cached["entries"]]
        entries: list[ListingEntry] = []
        total: int | None = None
        page = 1
        while True:
            html = await self._get(client, LISTING_PATH, listing_params(year, page))
            self.stats["listing_pages"] += 1
            rows, reported = parse_listing(html)
            total = total if total is not None else reported
            if not rows:
                break
            entries.extend(rows)
            if total is not None and len(entries) >= total:
                break
            page += 1
        complete = total is not None and len(entries) >= total
        self.archive.save_listing(year, entries, total, complete)
        log.info("listing %d: %d rows (reported %s)", year, len(entries), total)
        return entries

    async def fetch(self, years: list[int], courts: tuple[str, ...] = SUPREME_COURTS,
                    limit: int | None = None) -> dict:
        client = self._client or self._make_client()
        own = self._client is None
        self.archive.marker.unlink(missing_ok=True)
        try:
            for year in years:
                for entry in await self.walk_year(client, year):
                    if entry.court_code not in courts:
                        self.stats["out_of_scope"] += 1
                        continue
                    if self.archive.has(entry):
                        self.stats["skipped_existing"] += 1
                        continue
                    if limit is not None and self.stats["fetched"] >= limit:
                        if own:
                            await client.aclose()
                        return self.stats
                    try:
                        html = await self._get(client, JUDGMENT_PATH + entry.slug)
                    except Exception as exc:
                        self.stats["errors"] += 1
                        log.warning("could not fetch %s: %s", entry.slug, exc)
                        continue
                    self.archive.save_page(entry, html)
                    self.stats["fetched"] += 1
                    if self.stats["fetched"] % 50 == 0:
                        log.info("progress: %s", self.stats)
        finally:
            if own:
                await client.aclose()
        self.archive.marker.write_text(json.dumps(
            self.stats | {"finished_at": datetime.now(timezone.utc).isoformat()}))
        return self.stats


# ------------------------------------------------------------------ indexer

async def index_archive(ctx, limit: int | None = None,
                        progress: Callable[[dict], Any] | None = None) -> dict:
    """Ingest archived judgments not yet in the corpus; then the treatment pass."""
    from app.ingest.pipeline import ingest_judgment, run_treatment_pass

    archive = RawArchive(ctx.settings.data_dir / "raw" / "elitigation")
    known = {row["citation"] for row in await ctx.db.all_judgments()}
    todo = [rec for rec in archive.manifest() if rec["citation"] not in known]
    if limit is not None:
        todo = todo[:limit]
    stats = {"pending": len(todo), "indexed": 0, "chunks": 0, "failed": 0,
             "started_at": datetime.now(timezone.utc).isoformat()}
    for rec in todo:
        entry = ListingEntry(**{k: rec[k] for k in ListingEntry.__dataclass_fields__})
        path = archive.page_path(entry)
        try:
            j = parse_elitigation_judgment(path.read_text(encoding="utf-8"),
                                           entry=rec, source_url=entry.url)
            if not j.paragraphs:
                raise ValueError("no numbered paragraphs found")
            _, n = await ingest_judgment(ctx, j, fetched_at=rec.get("fetched_at"))
            stats["indexed"] += 1
            stats["chunks"] += n
        except Exception as exc:
            stats["failed"] += 1
            log.warning("index %s failed: %s", rec["slug"], exc)
        if progress and (stats["indexed"] + stats["failed"]) % 25 == 0:
            await progress(dict(stats))
    stats["treatment"] = await run_treatment_pass(ctx)
    stats["finished_at"] = datetime.now(timezone.utc).isoformat()
    await ctx.db.kv_set("last_judgment_index", stats["finished_at"])
    if progress:
        await progress(dict(stats))
    return stats


async def index_follow(ctx, progress=None, poll_seconds: float = 60.0) -> dict:
    """Index in batches while a fetch run is still adding pages; stop once the
    fetcher's completion marker exists and nothing is left pending."""
    archive = RawArchive(ctx.settings.data_dir / "raw" / "elitigation")
    totals = {"indexed": 0, "chunks": 0, "failed": 0, "batches": 0}
    while True:
        done_fetching = archive.marker.exists()
        stats = await index_archive(ctx, progress=progress)
        for k in ("indexed", "chunks", "failed"):
            totals[k] += stats[k]
        totals["batches"] += 1
        if progress:
            await progress(totals | {"last_batch": stats, "following": True})
        # pages that fail to parse stay "pending", so stop on no progress
        # rather than on an empty queue
        if done_fetching and stats["indexed"] == 0:
            return totals
        if stats["indexed"] == 0:
            await asyncio.sleep(poll_seconds)


# ------------------------------------------------------------------ CLI

async def _amain(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    if args.command == "fetch":
        years = list(range(args.to_year, args.from_year - 1, -1))  # newest first
        stats = await ELitigationFetcher(settings).fetch(years, limit=args.limit)
        log.info("fetch done: %s", stats)
    elif args.command == "status":
        archive = RawArchive(settings.data_dir / "raw" / "elitigation")
        recs = archive.manifest()
        by_court: dict[str, int] = {}
        for r in recs:
            by_court[r["court_code"]] = by_court.get(r["court_code"], 0) + 1
        print(json.dumps({"archived": len(recs), "by_court": by_court}, indent=2))
    elif args.command == "index":
        from app.context import build_context, shutdown_context

        ctx = await build_context(settings)
        try:
            log.info("index done: %s", await index_archive(ctx, limit=args.limit))
        finally:
            await shutdown_context(ctx)


def main() -> None:
    p = argparse.ArgumentParser(description="eLitigation judgments adapter")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download Supreme Court judgments into the raw archive")
    f.add_argument("--from-year", type=int, default=2000)
    f.add_argument("--to-year", type=int, default=date.today().year)
    f.add_argument("--limit", type=int, default=None, help="max judgments to download")
    i = sub.add_parser("index", help="index archived judgments (server must be stopped)")
    i.add_argument("--limit", type=int, default=None)
    sub.add_parser("status", help="summarise the raw archive")
    asyncio.run(_amain(p.parse_args()))


if __name__ == "__main__":
    main()

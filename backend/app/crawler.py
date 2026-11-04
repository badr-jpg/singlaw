"""SSO crawler.

SSO's terms of use permit automated extraction ONLY between 05:00 and 07:00
Singapore Time. The window guard is checked before *every* fetch and a hard
deadline kills the run at 07:00 — this is a legal constraint, not a politeness
setting, so there is deliberately no bypass flag for live crawling.

Two modes, both window-guarded, single connection, polite delays, exponential
backoff on any 4xx/5xx, persistent resumable state in SQLite:

- sync: incremental, driven by the "What's New" listing; ingests as it goes.
- crawl-full: builds the whole corpus. Walks SSO's browse listing of current
  Acts (optionally subsidiary legislation), queues every document, and saves
  each page gzip-compressed into the corpus archive (data/corpus) WITHOUT
  indexing, so the two-hour window is spent fetching. Index afterwards with
  `seed --archive ../data/corpus` at any time. Pages already in the archive are
  never fetched again, even if the SQLite crawl state was wiped by `make clean`.

Every page fetched in either mode is also saved to the archive, so the corpus
can be rebuilt offline and shipped with the submission.

CLI:
  python -m app.crawler seed --archive ../data/corpus    # index an archive, no crawling
  python -m app.crawler sync                             # one window-guarded incremental run
  python -m app.crawler schedule                         # sleep → sync daily
  python -m app.crawler crawl-full --wait                # wait for 05:00, crawl, repeat daily until done
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from app.config import Settings, get_settings
from app.ingest.archive import archive_relpath, extract_listing_links, save_to_archive

log = logging.getLogger(__name__)


class CrawlWindow:
    def __init__(self, start: str = "05:00", end: str = "07:00",
                 tz: str = "Asia/Singapore"):
        self.tz = ZoneInfo(tz)
        h, m = start.split(":")
        self.start = dtime(int(h), int(m))
        h, m = end.split(":")
        self.end = dtime(int(h), int(m))

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def is_open(self, at: datetime | None = None) -> bool:
        t = (at or self.now()).astimezone(self.tz).time()
        return self.start <= t < self.end

    def seconds_until_close(self, at: datetime | None = None) -> float:
        at = (at or self.now()).astimezone(self.tz)
        if not self.is_open(at):
            return 0.0
        close = at.replace(hour=self.end.hour, minute=self.end.minute,
                           second=0, microsecond=0)
        return (close - at).total_seconds()

    def seconds_until_open(self, at: datetime | None = None) -> float:
        at = (at or self.now()).astimezone(self.tz)
        if self.is_open(at):
            return 0.0
        nxt = at.replace(hour=self.start.hour, minute=self.start.minute,
                         second=0, microsecond=0)
        if nxt <= at:
            nxt += timedelta(days=1)
        return (nxt - at).total_seconds()


def window_from_settings(s: Settings) -> CrawlWindow:
    return CrawlWindow(s.crawl_window_start, s.crawl_window_end, s.crawl_tz)


class SSOCrawler:
    """`ctx` needs `.settings` and `.db`; only `sync` also needs the models and
    vector store (it ingests as it goes), so `crawl-full` runs on a light
    context and does not hold the embedded-Qdrant lock."""

    def __init__(self, ctx, window: CrawlWindow | None = None,
                 client: httpx.AsyncClient | None = None):
        self.ctx = ctx
        self.s = ctx.settings
        self.window = window or window_from_settings(ctx.settings)
        self._client = client

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            timeout=60.0, follow_redirects=True,
            headers={"User-Agent":
                     "sg-law-rag/0.1 (local legal-information assistant; "
                     "respects SSO 05:00-07:00 SGT extraction window)"})

    # ------------------------------------------------------------ guards

    def _deadline(self) -> float:
        return asyncio.get_event_loop().time() + self.window.seconds_until_close()

    def _may_fetch(self, deadline: float) -> bool:
        """Checked before EVERY request: window open and before the hard deadline."""
        return self.window.is_open() and asyncio.get_event_loop().time() < deadline

    async def _pause(self, seconds: float, deadline: float) -> None:
        await asyncio.sleep(min(seconds, max(0.0, deadline - asyncio.get_event_loop().time())))

    def _closed_result(self) -> dict:
        wait = self.window.seconds_until_open()
        return {"started": False,
                "reason": f"outside the permitted 05:00–07:00 SGT window; "
                          f"next window opens in {int(wait // 60)} min",
                "fetched": 0, "errors": 0}

    def _fetch_url(self, url: str, kind: str) -> str:
        """Legislation is fetched as the whole document so lazily loaded parts
        of long Acts are included (SSO_WHOLE_DOC_QUERY="" turns this off)."""
        q = self.s.sso_whole_doc_query
        if kind == "judgment" or not q:
            return url
        return f"{url}{'&' if '?' in url else '?'}{q}"

    # --------------------------------------------------------- discovery

    async def discover(self, client: httpx.AsyncClient) -> int:
        """Parse the What's New listing and enqueue changed documents.
        Never a full re-crawl."""
        url = urljoin(self.s.sso_base_url, self.s.sso_whats_new_path)
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        added = 0
        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            if "/Act/" in href or "/SL/" in href or "/Acts-Supp/" in href:
                await self.ctx.db.enqueue_url(
                    urljoin(self.s.sso_base_url, href.split("?")[0]), "legislation")
                added += 1
            elif "/judgments/" in href:
                await self.ctx.db.enqueue_url(
                    urljoin(self.s.judiciary_base_url, href.split("?")[0]), "judgment")
                added += 1
        return added

    async def discover_full(self, client: httpx.AsyncClient, deadline: float,
                            include_sl: bool = False) -> dict:
        """Walk SSO's browse listings breadth-first (pagination and letter
        filters included, capped by CRAWL_MAX_LISTING_PAGES) and enqueue every
        Act / SL document found. Re-running is cheap: the queue ignores
        duplicates."""
        starts = [(self.s.sso_browse_acts_path, "legislation")]
        if include_sl:
            starts.append((self.s.sso_browse_sl_path, "subsidiary_legislation"))
        stats = {"listing_pages": 0, "documents_found": 0, "errors": 0}
        for start_path, kind in starts:
            start = urljoin(self.s.sso_base_url, start_path)
            queue, seen = [start], {start}
            while queue and stats["listing_pages"] < self.s.crawl_max_listing_pages:
                if not self._may_fetch(deadline):
                    return stats
                page = queue.pop(0)
                try:
                    resp = await client.get(page)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("listing page failed (%s): %s", page, exc)
                    stats["errors"] += 1
                    await self._pause(self.s.crawl_delay_seconds, deadline)
                    continue
                stats["listing_pages"] += 1
                docs, more = extract_listing_links(resp.text, str(resp.url), start_path)
                for d in docs:
                    if kind == "legislation" and "/SL/" in d and not include_sl:
                        continue
                    await self.ctx.db.enqueue_url(
                        d, "subsidiary_legislation" if "/SL/" in d else "legislation")
                    stats["documents_found"] += 1
                for p in more:
                    if p not in seen:
                        seen.add(p)
                        queue.append(p)
                log.info("listing %s → %d documents, %d more pages queued",
                         page, len(docs), len(queue))
                await self._pause(self.s.crawl_delay_seconds, deadline)
        return stats

    # ------------------------------------------------------------ fetching

    async def _ingest(self, url: str, kind: str, html: str) -> None:
        from app.ingest.pipeline import ingest_judgment_html, ingest_legislation_html

        if kind == "judgment":
            await ingest_judgment_html(self.ctx, html, source_url=url)
        else:
            await ingest_legislation_html(
                self.ctx, html, source_url=url,
                doc_type="subsidiary_legislation" if kind == "subsidiary_legislation" else None)

    async def _process_queue(self, client: httpx.AsyncClient, deadline: float,
                             archive_only: bool) -> tuple[int, int, int]:
        fetched = errors = skipped = 0
        backoff = self.s.crawl_delay_seconds
        archive = Path(self.s.corpus_dir)
        attempted: set[str] = set()  # one attempt per URL per run: a bad URL can't block the queue
        while True:
            # hard kill at 07:00 — checked before every fetch
            if not self._may_fetch(deadline):
                log.info("crawl window closed — stopping (resumes next morning)")
                break
            pending = [p for p in await self.ctx.db.pending_urls(limit=len(attempted) + 50)
                       if p["url"] not in attempted]
            if not pending:
                break
            item = pending[0]
            url, kind = item["url"], item["kind"]
            attempted.add(url)
            if archive_only and (archive / archive_relpath(url, kind)).exists():
                await self.ctx.db.mark_url(url, "done")  # already saved earlier
                skipped += 1
                continue
            try:
                resp = await client.get(self._fetch_url(url, kind))
                if resp.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp)
                save_to_archive(archive, url, kind, resp.text)
                if not archive_only:
                    await self._ingest(url, kind, resp.text)
                await self.ctx.db.mark_url(url, "done", etag=resp.headers.get("etag"))
                fetched += 1
                backoff = self.s.crawl_delay_seconds
                if fetched % 25 == 0:
                    log.info("fetched %d documents this run", fetched)
            except Exception as exc:
                errors += 1
                await self.ctx.db.mark_url(url, "error", error=str(exc)[:300])
                backoff = min(backoff * 2, self.s.crawl_max_backoff_seconds)
                log.warning("fetch failed (%s), backing off %.0fs: %s", url, backoff, exc)
            await self._pause(backoff, deadline)
        return fetched, errors, skipped

    async def sync(self) -> dict:
        """One window-guarded incremental run. Resumable: state is in SQLite."""
        if not self.window.is_open():
            return self._closed_result()

        deadline = self._deadline()
        client = self._client or self._make_client()
        own_client = self._client is None
        errors = 0
        try:
            try:
                await self.discover(client)
            except httpx.HTTPError as exc:
                log.warning("What's New fetch failed: %s", exc)
                errors += 1
            fetched, errs, _ = await self._process_queue(client, deadline, archive_only=False)
            errors += errs
        finally:
            if own_client:
                await client.aclose()

        if fetched:
            from app.ingest.pipeline import run_treatment_pass

            await run_treatment_pass(self.ctx)
        await self.ctx.db.kv_set("last_sync", datetime.now(self.window.tz).isoformat())
        return {"started": True, "reason": "ok", "fetched": fetched, "errors": errors}

    async def crawl_full(self, include_sl: bool = False) -> dict:
        """One window-guarded full-corpus run: discover, then fetch into the
        archive. Run it again the next morning to continue where it stopped."""
        if not self.window.is_open():
            return self._closed_result()

        deadline = self._deadline()
        client = self._client or self._make_client()
        own_client = self._client is None
        try:
            found = await self.discover_full(client, deadline, include_sl=include_sl)
            fetched, errors, skipped = await self._process_queue(
                client, deadline, archive_only=True)
        finally:
            if own_client:
                await client.aclose()
        remaining = len(await self.ctx.db.pending_urls(limit=100000))
        await self.ctx.db.kv_set("last_crawl_full", datetime.now(self.window.tz).isoformat())
        return {"started": True, "reason": "ok", **found, "fetched": fetched,
                "already_archived": skipped, "errors": errors + found["errors"],
                "remaining": remaining}

    async def run_scheduler(self) -> None:
        """Sleep until the window opens, sync, repeat. Ctrl-C to stop."""
        while True:
            wait = self.window.seconds_until_open()
            if wait > 0:
                log.info("sleeping %.0f min until the 05:00 SGT window", wait / 60)
                await asyncio.sleep(wait)
            result = await self.sync()
            log.info("sync finished: %s", result)
            await asyncio.sleep(max(self.window.seconds_until_open(), 60))

    async def run_full_until_done(self, include_sl: bool = False, max_days: int = 4) -> dict:
        """Wait for the window, crawl, and repeat on following mornings until
        nothing is pending (or max_days windows have been used)."""
        result: dict = {}
        for day in range(1, max_days + 1):
            wait = self.window.seconds_until_open()
            if wait > 0:
                log.info("sleeping %.0f min until the 05:00 SGT window (day %d)", wait / 60, day)
                await asyncio.sleep(wait)
            result = await self.crawl_full(include_sl=include_sl)
            log.info("full crawl, day %d: %s", day, result)
            if result.get("started") and result.get("remaining", 1) == 0:
                break
            await asyncio.sleep(max(self.window.seconds_until_open(), 60))
        return result


# ------------------------------------------------------------------- CLI

async def _amain(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    if args.command == "crawl-full":
        # light context: SQLite only — no models, no Qdrant lock
        from app.db import Database

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        db = Database(settings.db_path)
        await db.open()
        try:
            crawler = SSOCrawler(SimpleNamespace(settings=settings, db=db))
            if args.wait:
                result = await crawler.run_full_until_done(args.include_sl, args.max_days)
            else:
                result = await crawler.crawl_full(include_sl=args.include_sl)
            log.info("%s", result)
        finally:
            await db.close()
        return

    from app.context import build_context, shutdown_context

    ctx = await build_context(settings)
    try:
        if args.command == "seed":
            from app.ingest.pipeline import seed_from_archive

            started = asyncio.get_event_loop().time()
            counts = await seed_from_archive(ctx, Path(args.archive).resolve())
            counts["seconds"] = round(asyncio.get_event_loop().time() - started, 1)
            log.info("seeded: %s", counts)
        elif args.command == "sync":
            result = await SSOCrawler(ctx).sync()
            log.info("%s", result)
        elif args.command == "schedule":
            await SSOCrawler(ctx).run_scheduler()
    finally:
        await shutdown_context(ctx)


def main() -> None:
    p = argparse.ArgumentParser(description="SSO crawler / corpus seeder")
    sub = p.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="load a pre-fetched archive (no crawling)")
    seed.add_argument("--archive", required=True,
                      help="directory containing manifest.json (--seed-from-archive)")
    sub.add_parser("sync", help="one incremental sync inside the 05:00–07:00 SGT window")
    sub.add_parser("schedule", help="run the scheduler: wait for the window daily")
    full = sub.add_parser("crawl-full",
                          help="full corpus crawl into the archive (05:00–07:00 SGT only)")
    full.add_argument("--include-sl", action="store_true",
                      help="also crawl subsidiary legislation (many more pages)")
    full.add_argument("--wait", action="store_true",
                      help="sleep until the window opens; repeat daily until nothing is pending")
    full.add_argument("--max-days", type=int, default=4,
                      help="with --wait: give up after this many windows (default 4)")
    asyncio.run(_amain(p.parse_args()))
    # torch/tokenizer worker threads are non-daemon and can outlive the loop;
    # everything is committed by now, so exit hard rather than hang.
    os._exit(0)


if __name__ == "__main__":
    main()

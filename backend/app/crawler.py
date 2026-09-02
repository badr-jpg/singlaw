"""SSO crawler.

SSO's terms of use permit automated extraction ONLY between 05:00 and 07:00
Singapore Time. The window guard is checked before *every* fetch and a hard
deadline kills the run at 07:00 — this is a legal constraint, not a politeness
setting, so there is deliberately no bypass flag for live crawling.

Incremental sync driven by the "What's New" listings; persistent crawl state
in SQLite so an interrupted run resumes the next morning; single connection;
polite delays; exponential backoff on any 4xx/5xx.

CLI:
  python -m app.crawler seed --archive ../data/archive   # no crawling
  python -m app.crawler sync                             # one window-guarded run
  python -m app.crawler schedule                         # sleep → sync daily
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from app.config import Settings, get_settings
from app.context import AppContext, build_context, shutdown_context
from app.ingest.pipeline import (
    ingest_judgment_html,
    ingest_legislation_html,
    run_treatment_pass,
    seed_from_archive,
)

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
    def __init__(self, ctx: AppContext, window: CrawlWindow | None = None,
                 client: httpx.AsyncClient | None = None):
        self.ctx = ctx
        self.s = ctx.settings
        self.window = window or window_from_settings(ctx.settings)
        self._client = client

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            timeout=30.0, follow_redirects=True,
            headers={"User-Agent":
                     "sg-law-rag/0.1 (local legal-information assistant; "
                     "respects SSO 05:00-07:00 SGT extraction window)"})

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

    async def _ingest(self, url: str, kind: str, html: str) -> None:
        if kind == "judgment":
            await ingest_judgment_html(self.ctx, html, source_url=url)
        else:
            await ingest_legislation_html(self.ctx, html, source_url=url)

    async def sync(self) -> dict:
        """One window-guarded incremental run. Resumable: state is in SQLite."""
        if not self.window.is_open():
            wait = self.window.seconds_until_open()
            return {"started": False,
                    "reason": f"outside the permitted 05:00–07:00 SGT window; "
                              f"next window opens in {int(wait // 60)} min",
                    "fetched": 0, "errors": 0}

        deadline = asyncio.get_event_loop().time() + self.window.seconds_until_close()
        fetched = errors = 0
        backoff = self.s.crawl_delay_seconds
        client = self._client or self._make_client()
        own_client = self._client is None
        try:
            try:
                await self.discover(client)
            except httpx.HTTPError as exc:
                log.warning("What's New fetch failed: %s", exc)
                errors += 1

            while True:
                # hard kill at 07:00 — checked before every fetch
                if (not self.window.is_open()
                        or asyncio.get_event_loop().time() >= deadline):
                    log.info("crawl window closed — stopping (resumes next morning)")
                    break
                pending = await self.ctx.db.pending_urls(limit=1)
                if not pending:
                    break
                item = pending[0]
                try:
                    resp = await client.get(item["url"])
                    if resp.status_code >= 400:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request,
                            response=resp)
                    await self._ingest(item["url"], item["kind"], resp.text)
                    await self.ctx.db.mark_url(
                        item["url"], "done", etag=resp.headers.get("etag"))
                    fetched += 1
                    backoff = self.s.crawl_delay_seconds
                except Exception as exc:
                    errors += 1
                    await self.ctx.db.mark_url(item["url"], "error", error=str(exc)[:300])
                    backoff = min(backoff * 2, self.s.crawl_max_backoff_seconds)
                    log.warning("fetch failed (%s), backing off %.0fs: %s",
                                item["url"], backoff, exc)
                await asyncio.sleep(min(backoff, max(0.0, deadline - asyncio.get_event_loop().time())))
        finally:
            if own_client:
                await client.aclose()

        if fetched:
            await run_treatment_pass(self.ctx)
        await self.ctx.db.kv_set("last_sync", datetime.now(self.window.tz).isoformat())
        return {"started": True, "reason": "ok", "fetched": fetched, "errors": errors}

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


# ------------------------------------------------------------------- CLI

async def _amain(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ctx = await build_context(get_settings())
    try:
        if args.command == "seed":
            counts = await seed_from_archive(ctx, Path(args.archive).resolve())
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
    asyncio.run(_amain(p.parse_args()))
    # torch/tokenizer worker threads are non-daemon and can outlive the loop;
    # everything is committed by now, so exit hard rather than hang.
    os._exit(0)


if __name__ == "__main__":
    main()

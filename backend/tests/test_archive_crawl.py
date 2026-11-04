import json
from types import SimpleNamespace

import httpx

from app.config import Settings
from app.crawler import CrawlWindow, SSOCrawler
from app.db import Database
from app.ingest.archive import (
    archive_relpath,
    extract_listing_links,
    read_archived,
    save_to_archive,
)

BASE = "https://sso.agc.gov.sg"
BROWSE = "/Browse/Act/Current/All?PageSize=500&SortBy=Title&SortOrder=ASC"

LISTING_1 = """<html><body>
<a href="/Act/EmA1968">Employment Act 1968</a>
<a href="/Act/PDPA2012?ProvIds=P1">PDPA</a>
<a href="/Act/EmA1968">duplicate</a>
<a href="/SL/EmA1968-RG1">Regs</a>
<a href="/Browse/Act/Current/All/1?PageSize=500">Next</a>
<a href="https://other.example/Act/X">offsite</a>
<a href="/Help">help</a>
</body></html>"""
LISTING_2 = '<html><body><a href="/Act/CA1961">Companies Act 1967</a></body></html>'
ACT = """<html><head><title>Employment Act 1968</title></head><body>
<div class="actHd">Employment Act 1968</div><p>1. This Act is the Employment Act 1968.</p>
</body></html>"""


def test_extract_listing_links():
    docs, pages = extract_listing_links(LISTING_1, BASE + BROWSE, BROWSE)
    assert docs == [f"{BASE}/Act/EmA1968", f"{BASE}/Act/PDPA2012", f"{BASE}/SL/EmA1968-RG1"]
    assert pages == [f"{BASE}/Browse/Act/Current/All/1?PageSize=500"]


def test_archive_relpath_and_roundtrip(tmp_path):
    assert archive_relpath(f"{BASE}/Act/EmA1968", "legislation") == "acts/EmA1968.html.gz"
    assert archive_relpath(f"{BASE}/SL/EmA1968-RG1", "legislation") == "sl/EmA1968-RG1.html.gz"
    rel = save_to_archive(tmp_path, f"{BASE}/Act/EmA1968", "legislation", ACT)
    save_to_archive(tmp_path, f"{BASE}/Act/EmA1968", "legislation", ACT)  # refresh, no dup
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert [d["path"] for d in manifest["documents"]] == [rel]
    assert manifest["documents"][0]["source_url"] == f"{BASE}/Act/EmA1968"
    assert read_archived(tmp_path / rel) == ACT


class OpenWindow(CrawlWindow):
    def is_open(self, at=None):
        return True

    def seconds_until_close(self, at=None):
        return 3600.0


async def test_crawl_full_archives_without_indexing(tmp_path):
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if req.url.path.startswith("/Browse/"):
            return httpx.Response(200, text=LISTING_2 if "/All/1" in req.url.path else LISTING_1)
        if req.url.path == "/Act/PDPA2012":
            return httpx.Response(503)
        return httpx.Response(200, text=ACT)

    settings = Settings(model_profile="stub", data_dir=tmp_path / "data",
                        corpus_dir=tmp_path / "corpus", crawl_delay_seconds=0,
                        crawl_max_backoff_seconds=0, _env_file=None)
    db = Database(settings.db_path)
    await db.open()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)
    crawler = SSOCrawler(SimpleNamespace(settings=settings, db=db),
                         window=OpenWindow(), client=client)
    try:
        r = await crawler.crawl_full()
        assert r["started"] and r["listing_pages"] == 2
        assert r["fetched"] == 2 and r["errors"] == 1  # PDPA 503 → error, retried next run
        assert f"{BASE}/Act/EmA1968?WholeDoc=1" in seen
        assert not any("/SL/" in u for u in seen)          # SL skipped without --include-sl
        assert (tmp_path / "corpus" / "acts" / "CA1961.html.gz").exists()

        # crawl state wiped (make clean) → archived pages are not fetched again
        await db.close()
        for f in settings.db_path.parent.glob(settings.db_path.name + "*"):
            f.unlink()
        db2 = Database(settings.db_path)
        await db2.open()
        crawler.ctx = SimpleNamespace(settings=settings, db=db2)
        seen.clear()
        r2 = await crawler.crawl_full()
        assert r2["already_archived"] == 2
        assert not any(u.endswith("/Act/EmA1968?WholeDoc=1") for u in seen)
        await db2.close()
    finally:
        await client.aclose()


async def test_crawl_full_refuses_outside_window(tmp_path):
    class Closed(CrawlWindow):
        def is_open(self, at=None):
            return False

    settings = Settings(model_profile="stub", data_dir=tmp_path, _env_file=None)
    crawler = SSOCrawler(SimpleNamespace(settings=settings, db=None), window=Closed())
    r = await crawler.crawl_full()
    assert r["started"] is False and "05:00" in r["reason"]

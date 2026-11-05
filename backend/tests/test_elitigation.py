import asyncio
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.context import AppContext, shutdown_context
from app.db import Database
from app.elitigation import (
    ELitigationFetcher,
    ListingEntry,
    RawArchive,
    index_archive,
    parse_listing,
    slug_to_citation,
)
from app.ingest.judgment_parser import parse_elitigation_judgment
from app.llm import NullProvider
from app.ml import ModelRegistry
from app.retrieval import retrieve
from app.vectorstore import VectorStore

FIX = Path(__file__).parent / "fixtures"
ENTRY = {"citation": "[2025] SGCA 7", "title": "ACME HOLDINGS PTE LTD v LEE MEI LING",
         "decision_date": "2025-03-14", "catchwords": ["Employment Law — Dismissal"]}


def test_slug_to_citation_restores_brackets():
    assert slug_to_citation("2026_SGHCA_26") == ("[2026] SGHC(A) 26", "SGHC(A)", 2026)
    assert slug_to_citation("2025_SGCAI_5") == ("[2025] SGCA(I) 5", "SGCA(I)", 2025)
    assert slug_to_citation("2024_SGHC_103") == ("[2024] SGHC 103", "SGHC", 2024)
    assert slug_to_citation("not-a-slug") is None


def test_parse_listing_rows_and_total():
    entries, total = parse_listing((FIX / "elit_listing_p1.html").read_text())
    assert total == 3
    first = entries[0]
    assert first.slug == "2025_SGCA_7" and first.citation == "[2025] SGCA 7"
    assert first.decision_date == "2025-03-14"
    assert first.case_number == "CA/CA 12/2024"
    assert first.catchwords == ["Employment Law — Dismissal"]
    assert entries[1].court_code == "SGDC"


def test_parse_elitigation_judgment():
    j = parse_elitigation_judgment((FIX / "elit_judgment.html").read_text(), entry=ENTRY,
                                   source_url="https://www.elitigation.sg/gd/s/2025_SGCA_7")
    assert j.neutral_citation == "[2025] SGCA 7"
    assert j.court == "Court of Appeal" and j.court_level == 5
    assert j.case_name == "Acme Holdings Pte Ltd v Lee Mei Ling"
    assert str(j.decision_date) == "2025-03-14"
    assert j.coram == ["Judith Prakash", "Steven Chong"]
    assert [p.number for p in j.paragraphs] == [1, 2, 3, 9]  # forward jumps accepted
    assert j.paragraphs[0].text.startswith("[Introduction] This appeal")
    assert not j.paragraphs[0].text.rstrip(".").endswith("1")  # footnote marker removed
    assert "due inquiry" in j.paragraphs[1].text  # quote continues its paragraph
    last = j.paragraphs[-1].text
    assert last.startswith("[Conclusion]")
    assert "LLP" not in last and "Record of Appeal" not in last and "Justice" not in last
    assert j.disposition and "dismiss the appeal" in j.disposition
    assert set(j.cites) == {"[2015] SGHC 112", "[2018] SGHC 44"}


def _fake_site():
    """MockTransport serving two listing pages and the judgments, 503 once."""
    calls = {"judgment": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gd/Home/Index":
            page = request.url.params["CurrentPage"]
            return httpx.Response(200, text=(FIX / f"elit_listing_p{page}.html").read_text())
        if request.url.path.startswith("/gd/s/"):
            calls["judgment"] += 1
            if calls["judgment"] == 1:
                return httpx.Response(503)  # transient: must back off and retry
            return httpx.Response(200, text=(FIX / "elit_judgment.html").read_text())
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


async def _noop_sleep(_s):
    return None


async def test_fetcher_scopes_retries_and_resumes(tmp_path):
    settings = Settings(model_profile="stub", data_dir=tmp_path, _env_file=None)
    transport, calls = _fake_site()
    client = httpx.AsyncClient(transport=transport, base_url="https://www.elitigation.sg")
    f = ELitigationFetcher(settings, client=client, sleep=_noop_sleep)
    stats = await f.fetch([2025])
    assert stats["listing_pages"] == 2
    assert stats["fetched"] == 2           # SGCA + SGHC(A); SGDC is out of scope
    assert stats["out_of_scope"] == 1
    assert calls["judgment"] == 3          # one 503 retried
    archive = RawArchive(tmp_path / "raw" / "elitigation")
    assert {r["citation"] for r in archive.manifest()} == {"[2025] SGCA 7", "[2025] SGHC(A) 3"}

    again = await ELitigationFetcher(settings, client=client, sleep=_noop_sleep).fetch([2025])
    assert again["fetched"] == 0 and again["skipped_existing"] == 2  # resumable
    await client.aclose()


@pytest.fixture
async def fresh_ctx(tmp_path):
    settings = Settings(model_profile="stub", data_dir=tmp_path, _env_file=None)
    db = Database(settings.db_path)
    await db.open()
    registry = ModelRegistry(settings)
    await registry.load()
    store = VectorStore(settings.qdrant_path)
    await store.ensure_collections(registry.embedder.dim)
    ctx = AppContext(settings=settings, db=db, store=store, registry=registry, llm=NullProvider())
    yield ctx
    await shutdown_context(ctx)


async def test_index_archive_ingests_once_and_builds_graph(fresh_ctx):
    archive = RawArchive(fresh_ctx.settings.data_dir / "raw" / "elitigation")
    entry = ListingEntry(slug="2025_SGCA_7", citation="[2025] SGCA 7", court_code="SGCA",
                         year=2025, title=ENTRY["title"], decision_date="2025-03-14",
                         catchwords=ENTRY["catchwords"])
    archive.save_page(entry, (FIX / "elit_judgment.html").read_text())

    stats = await index_archive(fresh_ctx)
    assert stats["indexed"] == 1 and stats["failed"] == 0 and stats["chunks"] >= 1
    j = await fresh_ctx.db.get_judgment("[2025] SGCA 7")
    assert j and j["court_code"] == "SGCA"
    citing = await fresh_ctx.db.citing_of("[2015] SGHC 112")
    assert any(c["citation"] == "[2025] SGCA 7" and c["treatment_hint"] == "overruled" for c in citing)

    r = await retrieve(fresh_ctx, "summary dismissal without due inquiry employment act appeal")
    assert any(c.payload.citation.startswith("[2025] SGCA 7") for c in r.chunks)
    assert r.chunks and r.chunks[0].payload.source_url.endswith("/gd/s/2025_SGCA_7")

    again = await index_archive(fresh_ctx)
    assert again["pending"] == 0  # already-indexed judgments are skipped


async def test_fetch_writes_completion_marker(tmp_path):
    settings = Settings(model_profile="stub", data_dir=tmp_path, _env_file=None)
    transport, _ = _fake_site()
    client = httpx.AsyncClient(transport=transport, base_url="https://www.elitigation.sg")
    f = ELitigationFetcher(settings, client=client, sleep=_noop_sleep)
    await f.fetch([2025], limit=1)
    assert not f.archive.marker.exists()  # a limited run is not complete
    await f.fetch([2025])
    assert f.archive.marker.exists()
    await client.aclose()


# ------------------------------------------------------- pre-2004 page layouts

def test_parse_legacy_numbered_layout():
    entry = {"citation": "[2002] SGHC 9", "title": "TAN AH KOW v LIM BEE HOON",
             "decision_date": "2002-01-10"}
    j = parse_elitigation_judgment((FIX / "elit_legacy_numbered.html").read_text(), entry=entry)
    assert j.numbered and j.coram == ["Lai Kew Chai J"]
    assert [p.number for p in j.paragraphs] == [1, 2, 3]  # "1 text" and "2. text" both
    assert j.paragraphs[0].text.startswith("[Introduction] The plaintiff")
    assert "next week" in j.paragraphs[0].text  # quote stays with its paragraph
    assert j.paragraphs[1].text.startswith("[Facts] The defendant")
    assert "Cur Adv Vult" not in " ".join(p.text for p in j.paragraphs)
    assert "Counsel" not in " ".join(p.text for p in j.paragraphs)
    assert j.cites == ["[1999] SGHC 12"]
    assert j.disposition and "dismissed" in j.disposition


def test_parse_legacy_unnumbered_layout_never_invents_pinpoints():
    from app.ingest.chunker import chunk_judgment

    entry = {"citation": "[2000] SGCA 3", "title": "GOH KIM SENG v PUBLIC PROSECUTOR"}
    j = parse_elitigation_judgment((FIX / "elit_legacy_unnumbered.html").read_text(), entry=entry)
    assert not j.numbered
    assert j.coram == ["Chao Hick Tin JA", "L P Thean JA", "Yong Pung How CJ"]
    assert len(j.paragraphs) == 3 and "Exhibit P1" in j.paragraphs[1].text
    assert j.disposition == "Appeal dismissed."
    chunks = chunk_judgment(j, max_chars=60)
    assert len(chunks) > 1
    for c in chunks:
        assert c.citation == "[2000] SGCA 3"  # no "at [n]"
        assert not c.text.startswith("[") and "paragraph" not in c.context
        assert ":part" in c.chunk_id


async def test_index_follow_stops_when_only_unparseable_pages_remain(fresh_ctx):
    from app.elitigation import index_follow

    archive = RawArchive(fresh_ctx.settings.data_dir / "raw" / "elitigation")
    entry = ListingEntry(slug="2025_SGCA_9", citation="[2025] SGCA 9", court_code="SGCA",
                         year=2025, title="X v Y", decision_date="2025-01-02")
    archive.save_page(entry, "<html><body><p>nothing numbered here</p></body></html>")
    archive.marker.write_text("{}")
    totals = await asyncio.wait_for(index_follow(fresh_ctx, poll_seconds=0), timeout=10)
    assert totals["failed"] == 1 and totals["indexed"] == 0

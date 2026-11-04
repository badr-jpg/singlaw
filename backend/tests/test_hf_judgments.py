import json

from app.ingest.hf_judgments import (
    HF_DATASET_URL,
    MIN_NUMBERED,
    build_judgment,
    chunks_for_row,
    split_paragraphs,
)


def _judgment_text(n: int = 12, words: int = 60) -> str:
    body = " ".join(["The appellant argued that the contract was valid."] * (words // 8))
    lines = ["Steven Chong JCA (delivering the judgment of the court):", "Introduction"]
    for i in range(1, n + 1):
        lines.append(f"{i} {body} See [2019] SGCA 12.")
        if i == 4:
            lines.append("Issues on appeal")          # heading → joins para 4
            lines.append("2015 was the relevant year.")  # implausible number → joins para 4
    return "\n".join(lines)


def test_split_paragraphs_numbered_lines():
    pre, paras = split_paragraphs(_judgment_text())
    assert pre.startswith("Steven Chong JCA")
    assert [p.number for p in paras] == list(range(1, 13))
    assert "Issues on appeal" in paras[3].text and "2015 was" in paras[3].text


def test_split_paragraphs_recovers_inline_numbering():
    text = " ".join(f"{i} The court considered point {i} in detail." for i in range(1, 9))
    _, paras = split_paragraphs(text)
    assert [p.number for p in paras] == list(range(1, 9))


def test_build_judgment_labels_and_cites():
    j = build_judgment({"_id": "abc123", "title": "", "text": _judgment_text()})
    assert j.neutral_citation == "MLEB-abc123"
    assert j.court_code == "" and j.source_url == HF_DATASET_URL
    assert "[2019] SGCA 12" in j.cites
    assert j.paragraphs[0].text.startswith("Steven Chong JCA")  # preamble kept


def test_build_judgment_decodes_mleb_id():
    j = build_judgment({"_id": "text_2002_SGCA_19", "text": _judgment_text()})
    assert j.neutral_citation == "[2002] SGCA 19" and j.court_code == "SGCA"
    assert j.court == "Court of Appeal" and j.court_level == 5


def test_build_judgment_uses_real_citation_in_id():
    j = build_judgment({"_id": "[2021] SGHC 45", "text": _judgment_text()})
    assert j.neutral_citation == "[2021] SGHC 45" and j.court_code == "SGHC"


def test_chunks_respect_max_chars_and_ids_are_stable():
    row = {"_id": "x1", "text": _judgment_text(n=30, words=80)}
    j, chunks = chunks_for_row(row, max_chars=1500)
    assert len(j.paragraphs) >= MIN_NUMBERED and len(chunks) > 3
    assert all(c.doc_type == "judgment" and c.source_url == HF_DATASET_URL for c in chunks)
    assert all(len(c.text) <= 1500 + 600 for c in chunks)  # one paragraph may overrun
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    _, again = chunks_for_row(row, max_chars=1500)
    assert [c.chunk_id for c in again] == [c.chunk_id for c in chunks]


def test_unnumbered_text_falls_back_to_sentence_windows():
    text = " ".join(["This judgment has no paragraph numbers at all."] * 200)
    j, chunks = chunks_for_row({"_id": "nonum", "text": text}, max_chars=1000)
    assert len(j.paragraphs) < MIN_NUMBERED
    assert len(chunks) > 5 and all(len(c.text) <= 1000 for c in chunks)
    assert chunks[0].chunk_id.endswith(":part1")


async def test_seed_judgments_jsonl(tmp_path):
    """Own throwaway index, so the shared session corpus other tests rely on is untouched."""
    from app.config import Settings
    from app.context import AppContext, shutdown_context
    from app.db import Database
    from app.ingest.pipeline import seed_from_archive
    from app.llm import NullProvider
    from app.ml import ModelRegistry
    from app.vectorstore import SG_LAW, VectorStore

    settings = Settings(model_profile="stub", data_dir=tmp_path / "data", _env_file=None)
    db = Database(settings.db_path)
    await db.open()
    registry = ModelRegistry(settings)
    await registry.load()
    store = VectorStore(settings.qdrant_path)
    await store.ensure_collections(registry.embedder.dim)
    ctx = AppContext(settings=settings, db=db, store=store, registry=registry, llm=NullProvider())

    archive = tmp_path / "corpus"
    (archive / "hf").mkdir(parents=True)
    rows = [{"_id": f"t{i}", "title": "", "text": _judgment_text(n=10)} for i in range(3)]
    (archive / "hf" / "corpus.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (archive / "manifest.json").write_text(json.dumps({"documents": [
        {"path": "hf/corpus.jsonl", "kind": "judgments_jsonl", "max_chars": 1500},
        {"path": "acts/missing.html.gz", "kind": "legislation"},
    ]}))
    try:
        counts = await seed_from_archive(ctx, archive)
        assert counts["judgments_jsonl_docs"] == 3 and counts["missing_files"] == 1
        assert await ctx.store.count(SG_LAW) == counts["chunks"] > 0
        hits = await ctx.store.by_doc_id(SG_LAW, "mleb-t0-singapore-judgment")  # non-MLEB id → label
        assert hits and hits[0]["source_url"] == HF_DATASET_URL
    finally:
        await shutdown_context(ctx)

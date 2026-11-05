"""The badlaldh/singapore-judgments passage loader."""
import json

import pytest

from app.ingest.hf_judgments import all_chunks, chunks_for_judgment, iter_judgments, judgment_from_rows


def _row(part, total=2, para=(1, 2), text="The duty of care in [2018] SGCA 1 applies."):
    return {"doc_id": f"2020_SGHC_5-{part:04d}", "part": part, "parts_total": total,
            "text": text, "word_count": 8, "para_start": para[0], "para_end": para[1],
            "citation": "[2020] SGHC 5", "case_name": "Tan v Lim", "court_code": "SGHC",
            "court": "General Division of the High Court", "year": 2020,
            "decision_date": "2020-03-07", "coram": ["A Judge"],
            "catchwords": ["Tort — Negligence — Duty of care"],
            "source_url": "https://www.elitigation.sg/gd/s/2020_SGHC_5"}


def _write(tmp_path, rows):
    p = tmp_path / "passages.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def test_one_chunk_per_passage_with_range_pinpoints(tmp_path):
    p = _write(tmp_path, [_row(2, para=(3, 3)), _row(1)])  # out of order on disk
    chunks = all_chunks(p)
    assert [c.chunk_id for c in chunks] == ["2020-sghc-5-tan-v-lim:part1", "2020-sghc-5-tan-v-lim:part2"]
    assert chunks[0].citation == "[2020] SGHC 5 at [1]–[2]"
    assert chunks[1].citation == "[2020] SGHC 5 at [3]"
    assert chunks[0].doc_type == "judgment" and chunks[0].court_level == 3
    assert chunks[0].cites == ["[2018] SGCA 1"]
    assert "paragraphs [1]–[2] of the judgment in Tan v Lim [2020] SGHC 5" in chunks[0].context
    assert "decided 7 March 2020" in chunks[0].context  # no zero padding, on any platform
    assert "Catchwords: Tort — Negligence — Duty of care" in chunks[0].context


def test_passages_sharing_a_paragraph_keep_distinct_ids(tmp_path):
    rows = [_row(1, para=(4, 4)), _row(2, para=(4, 4))]
    j = judgment_from_rows(rows)
    a, b = chunks_for_judgment(j, rows)
    assert a.citation == b.citation and a.chunk_id != b.chunk_id
    assert not j.numbered  # citation edges must not claim a paragraph


def test_missing_part_stops_rather_than_indexing_partially(tmp_path):
    p = _write(tmp_path, [_row(1, total=3), _row(3, total=3)])
    with pytest.raises(ValueError, match=r"expected parts 1\.\.3"):
        list(iter_judgments(p))


async def test_seed_registers_judgment_and_edges(tmp_path):
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
    (archive / "hf_judgments").mkdir(parents=True)
    _write(archive / "hf_judgments", [_row(1), _row(2, para=(3, 3))])
    (archive / "manifest.json").write_text(json.dumps({"documents": [
        {"path": "hf_judgments/passages.jsonl", "kind": "hf_judgment_passages"}]}))
    try:
        counts = await seed_from_archive(ctx, archive)
        assert counts["judgment"] == 1 and counts["chunks"] == 2
        assert await ctx.store.count(SG_LAW) == 2
        assert [r["citation"] for r in await ctx.db.all_judgments()] == ["[2020] SGHC 5"]
        edges = await ctx.db.citing_of("[2018] SGCA 1")
        assert edges and edges[0]["citation"] == "[2020] SGHC 5" and edges[0]["paragraph"] is None
    finally:
        await shutdown_context(ctx)

import csv
import json

from app.ingest.hf_elitigation import all_chunks, chunk_for_passage, iter_passages


def _row(part, para_start=None, para_end=None, **kw):
    base = {"doc_id": "2019_SGCA_12", "part": part, "parts_total": 3,
            "text": f"Passage {part}. The duty of care was breached; see [2007] SGCA 40.",
            "word_count": 12, "para_start": para_start, "para_end": para_end,
            "citation": "[2019] SGCA 12", "case_name": "Tan Ah Kow v Lim Bee Hoon",
            "court_code": "SGCA", "court": "Court of Appeal", "year": 2019,
            "decision_date": "2019-03-14", "coram": ["Sundaresh Menon CJ"],
            "catchwords": ["Tort — Negligence — Duty of care"],
            "source_url": "https://www.elitigation.sg/gd/s/2019_SGCA_12"}
    return {**base, **kw}


def test_passage_becomes_one_cited_chunk():
    c = chunk_for_passage(_row(2, 14, 19))
    assert c.chunk_id == "2019-sgca-12-tan-ah-kow-v-lim-bee-hoon:part2"
    assert c.citation == "[2019] SGCA 12 at [14]–[19]"
    assert c.doc_type == "judgment" and c.authority_tier == 4 and c.court_level == 5
    assert c.decision_date.isoformat() == "2019-03-14"
    assert "paragraphs [14]–[19] of the judgment in Tan Ah Kow v Lim Bee Hoon" in c.context
    assert "Catchwords: Tort — Negligence — Duty of care." in c.context
    assert c.cites == ["[2007] SGCA 40"]


def test_passage_without_paragraph_numbers_cites_the_part():
    c = chunk_for_passage(_row(3, court_code="SGHC", court="General Division of the High Court"))
    assert c.citation == "[2019] SGCA 12 (part 3)" and "part 3 of 3" in c.context
    assert c.authority_tier == 5  # High Court: not binding tier


def test_iter_passages_skips_other_subsets_and_duplicates(tmp_path):
    (tmp_path / "judgments").mkdir()
    rows = [_row(1, 1, 4), _row(2, 5, 9), _row(2, 5, 9)]  # last one is a duplicate
    (tmp_path / "judgments" / "train.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    leg = tmp_path / "legislation" / "work-family"
    leg.mkdir(parents=True)
    with (leg / "inventory.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["law", "section", "text"])
        w.writeheader()
        w.writerow({"law": "Employment Act 1968", "section": "38", "text": "Rest days"})
    got = list(iter_passages(tmp_path))
    assert [r["part"] for r in got] == [1, 2]
    assert [c.chunk_id.split(":")[1] for c in all_chunks(tmp_path)] == ["part1", "part2"]


def test_chunk_ids_are_stable():
    assert chunk_for_passage(_row(1, 1, 4)).chunk_id == chunk_for_passage(_row(1, 1, 4)).chunk_id


async def test_seed_indexes_passages_and_acts(tmp_path):
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

    corpus = tmp_path / "corpus"
    (corpus / "elitigation_hf").mkdir(parents=True)
    (corpus / "elitigation_hf" / "train.jsonl").write_text(
        "\n".join(json.dumps(_row(k, 3 * k - 2, 3 * k)) for k in (1, 2, 3)))
    (corpus / "manifest.json").write_text(json.dumps({"documents": [
        {"path": "elitigation_hf", "kind": "elitigation_passages"}]}))
    try:
        counts = await seed_from_archive(ctx, corpus)
        assert counts["judgment"] == 1 and counts["chunks"] == 3
        assert await ctx.store.count(SG_LAW) == 3
        judgments = await ctx.db.all_judgments()
        assert [j["citation"] for j in judgments] == ["[2019] SGCA 12"]
    finally:
        await shutdown_context(ctx)

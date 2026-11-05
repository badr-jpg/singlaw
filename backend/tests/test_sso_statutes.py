import json

from app.ingest.sso_statutes import (
    HF_STATUTES_URL,
    all_chunks,
    chunks_for_document,
    iter_documents,
    normalise_doc_type,
    section_number_and_heading,
)


def _row(doc, title, text, doc_type="Act", part="PART 1 PRELIMINARY", parent=None):
    return {"doc_name": doc, "doc_type": doc_type, "parent_act": parent,
            "section_title": title, "part": part, "division": None, "pages": [1], "text": text}


def test_section_number_parsing():
    assert section_number_and_heading({"section_title": "14. Termination of contract"}) == ("14", "Termination of contract")
    assert section_number_and_heading({"section_title": "Section 2A — Interpretation"}) == ("2A", "Interpretation")
    assert section_number_and_heading({"section_title": "Short title", "text": "1. This Act is …"}) == ("1", "Short title")
    assert section_number_and_heading({"section_title": "Schedule", "text": "Rules"}) == (None, "Schedule")


def test_doc_type_normalisation():
    assert normalise_doc_type("Act") == "act"
    assert normalise_doc_type("SL") == "subsidiary_legislation"
    assert normalise_doc_type("Subsidiary Legislation") == "subsidiary_legislation"


def test_chunks_cite_sections_and_split_long_ones():
    long = " ".join(f"({i}) An employer must pay the salary within 7 days of the end of the period." for i in range(1, 120))
    rows = [_row("Employment Act 1968", "1. Short title", "1. This Act is the Employment Act 1968."),
            _row("Employment Act 1968", "14. Termination", "14.—" + long),
            _row("Employment Act 1968", "14. Termination", "duplicate row text")]
    chunks = chunks_for_document("Employment Act 1968", rows, max_chars=1500)
    assert chunks[0].chunk_id == "employment-act-1968:s1"
    assert chunks[0].citation == "Employment Act 1968, s 1"
    assert chunks[0].doc_type == "act" and chunks[0].authority_tier == 2
    assert chunks[0].source_url == HF_STATUTES_URL and "check SSO" in chunks[0].context
    parts = [c for c in chunks if c.chunk_id.startswith("employment-act-1968:s14.")]
    assert len(parts) > 2 and all(len(c.text) <= 1500 for c in parts)
    assert parts[1].text.startswith("(")  # split at a subsection boundary
    assert len({c.chunk_id for c in chunks}) == len(chunks)  # duplicate number kept unique


def test_oversized_subsection_is_split_at_sentences_then_words():
    sentence = "An employer must pay the salary within seven days. "
    text = "(1) " + sentence * 60 + "(2) " + "x" * 10 + " word" * 400
    chunks = chunks_for_document("Employment Act 1968", [_row("Employment Act 1968", "14. Pay", text)],
                                 max_chars=500)
    assert len(chunks) > 3 and all(len(c.text) <= 500 for c in chunks)
    assert " ".join(c.text for c in chunks).split() == text.split()  # nothing lost


async def test_seed_statutes_and_report_missing_files(tmp_path):
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
    (archive / "sso_statutes").mkdir(parents=True)
    rows = [_row("Employment Act 1968", "1. Short title", "1. This Act is the Employment Act 1968."),
            _row("Employment Act 1968", "2. Interpretation", "2. In this Act, words mean things.")]
    (archive / "sso_statutes" / "sections.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (archive / "manifest.json").write_text(json.dumps({"documents": [
        {"path": "sso_statutes/sections.jsonl", "kind": "sso_statutes_jsonl", "doc_types": ["act"]},
        {"path": "acts/missing.html.gz", "kind": "legislation"},
    ]}))
    try:
        counts = await seed_from_archive(ctx, archive)
        assert counts["legislation"] == 1 and counts["missing_files"] == 1
        assert await ctx.store.count(SG_LAW) == counts["chunks"] == 2
        hits = await ctx.store.by_doc_id(SG_LAW, "employment-act-1968")
        assert hits and hits[0]["source_url"] == HF_STATUTES_URL
    finally:
        await shutdown_context(ctx)


def test_iter_documents_filters_and_groups(tmp_path):
    rows = [_row("Employment Act 1968", "1. Short title", "text a"),
            _row("Employment Act 1968", "2. Interpretation", "text b"),
            _row("Employment (Part-Time) Regulations", "1. Citation", "text c", doc_type="SL",
                 parent="Employment Act 1968"),
            _row("Personal Data Protection Act 2012", "1. Short title", "text d")]
    p = tmp_path / "sections.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    docs = [(n, len(r)) for n, r in iter_documents(p, ["act"])]
    assert docs == [("Employment Act 1968", 2), ("Personal Data Protection Act 2012", 1)]
    sl = all_chunks(p, doc_types=["subsidiary_legislation"])
    assert len(sl) == 1 and sl[0].doc_type == "subsidiary_legislation" and sl[0].authority_tier == 3
    assert "made under the Employment Act 1968" in sl[0].context


COVER = ("THE STATUTES OF THE REPUBLIC OF SINGAPORE\nAGENCY FOR SCIENCE,\nTECHNOLOGY AND RESEARCH\n"
         "ACT 1990\n2020 REVISED EDITION\nInformal Consolidation – version in force from 9/6/2025\n"
         "Agency for Science,\nTechnology and Research\nAct 1990\nARRANGEMENT OF SECTIONS\nSection\n1.\nShort title")


def test_front_matter_recovers_name_and_version():
    from datetime import date

    from app.ingest.sso_statutes import front_matter
    name, version = front_matter({"text": COVER}, "Agency for Science, Technology and Research Act 19")
    assert name == "Agency for Science, Technology and Research Act 1990"
    assert version == date(2025, 6, 9)
    upper = "GAMBLING REGULATORY AUTHORITY\nOF SINGAPORE ACT 2022\n(No. 14 of 2022)\nARRANGEMENT OF SECTIONS"
    assert front_matter({"text": upper}, "Gambling Regulatory Authority of Singapore Act 202")[0] \
        == "Gambling Regulatory Authority of Singapore Act 2022"


def test_page_furniture_is_removed_mid_sentence():
    from app.ingest.sso_statutes import strip_page_furniture
    raw = ("in conjunction\nwith\nany\nEmployment Act 1968\n2020 Ed.\n8\n"
           "Informal Consolidation – version in force from 5/12/2025\nconstructional work")
    assert " ".join(strip_page_furniture(raw, "Employment Act 1968").split()) \
        == "in conjunction with any constructional work"


def test_cover_rows_split_documents_and_detect_regulations(tmp_path):
    rows = [_row("Protection from Online Falsehoods and Manipulation", "Unsectioned",
                 "THE STATUTES OF THE REPUBLIC OF SINGAPORE\nX\nARRANGEMENT OF SECTIONS"),
            _row("Protection from Online Falsehoods and Manipulation", "1. Short title", "1. This Act …"),
            _row("Protection from Online Falsehoods and Manipulation", "Unsectioned",
                 "First published in the Government Gazette\nARRANGEMENT OF REGULATIONS"),
            _row("Protection from Online Falsehoods and Manipulation", "1. Citation", "1. These Regulations …"),
            _row("Employment Act 1968", "FIRST SCHEDULE", "Section 2 WORKMEN (1) Cleaners.", part="PART 16 X")]
    p = tmp_path / "sections.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    acts = list(iter_documents(p, ["act"]))
    assert [len(r) for _, r in acts] == [2, 1]           # the Regulations were split off and dropped
    sch = chunks_for_document(*acts[1])[0]
    assert sch.chunk_id == "employment-act-1968:sch-first" and sch.citation == "Employment Act 1968, First Schedule"
    assert "PART 16" not in sch.context                   # schedules don't inherit the last Part

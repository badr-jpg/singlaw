import json

import pytest

from app.ingest.sso_statutes import (
    SSO_URL,
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
    assert chunks[0].source_url == SSO_URL and "check SSO" in chunks[0].context
    assert "published copy" in chunks[0].context
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


def test_schedule_paragraphs_are_not_cited_as_sections():
    act = "Test Act 2000"
    rows = [_row(act, "1. Short title", "1. This Act is the Test Act."),
            _row(act, "12. First Schedule amended", "12. The First Schedule is amended."),
            _row(act, "First Schedule amended", "13. The First Schedule is amended again."),
            _row(act, "FIRST SCHEDULE", "1. Fees payable are $5."),
            _row(act, "FIRST SCHEDULE — continue", "2. Further fees are $9."),
            _row(act, "THE SCHEDULE", "1. Other fees."),
            _row(act, "2000 Revised Edition note", "Editorial note.")]
    citations = [c.citation for c in chunks_for_document(act, rows)]
    assert citations[:3] == [f"{act}, s 1", f"{act}, s 12", f"{act}, s 13"]
    assert citations[3:6] == [f"{act}, First Schedule", f"{act}, First Schedule", f"{act}, Schedule"]
    assert citations[6] == f"{act}, 2000 Revised Edition note"


def _cover(name, kind="SECTIONS"):
    return _row(name, "Unsectioned", f"THE STATUTES OF THE REPUBLIC OF SINGAPORE\nARRANGEMENT OF {kind}")


def test_same_named_documents_keep_separate_ids(tmp_path):
    name = "Very Long Name That The Dataset Cut Off At Fifty C"
    rows = [_cover(name, "REGULATIONS"), _row(name, "1. Citation", "1. Regulations text."),
            _cover(name), _row(name, "1. Short title", "1. First Act text."),
            _cover(name), _row(name, "1. Short title", "1. Second Act text."),
            _cover("Other Act 2000"), _row("Other Act 2000", "1. Short title", "1. Other text.")]
    p = tmp_path / "sections.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    slug = "very-long-name-that-the-dataset-cut-off-at-fifty-c"

    by_id = {c.chunk_id: c.text for c in all_chunks(p)}
    assert len(by_id) == 4  # nothing overwritten
    assert by_id[f"{slug}:s1"] == "1. First Act text."  # an Act keeps the plain id
    assert by_id[f"{slug}-2:s1"] == "1. Second Act text."
    assert by_id[f"{slug}-3:s1"] == "1. Regulations text."
    assert by_id["other-act-2000:s1"] == "1. Other text."

    # same ids whichever types are indexed, so eval labels stay valid
    acts = {c.chunk_id for c in all_chunks(p, doc_types=["act"])}
    assert acts == {f"{slug}:s1", f"{slug}-2:s1", "other-act-2000:s1"}
    sl = all_chunks(p, doc_types=["subsidiary_legislation"])
    assert [c.chunk_id for c in sl] == [f"{slug}-3:s1"]
    assert len(all_chunks(p, doc_types=["act"], limit=1)) == 1


async def test_seed_statutes_and_stop_on_missing_files(tmp_path):
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
    statutes = {"path": "sso_statutes/sections.jsonl", "kind": "sso_statutes_jsonl", "doc_types": ["act"]}
    (archive / "manifest.json").write_text(json.dumps({"documents": [
        statutes, {"path": "sso_statutes/missing.jsonl", "kind": "sso_statutes_jsonl"},
    ]}))
    try:
        # a missing file stops the seed before anything is indexed
        with pytest.raises(FileNotFoundError, match=r"sso_statutes/missing\.jsonl.*docs/CORPUS\.md"):
            await seed_from_archive(ctx, archive)
        assert await ctx.store.count(SG_LAW) == 0
        assert await ctx.db.kv_get("last_seed") is None

        (archive / "manifest.json").write_text(json.dumps({"documents": [statutes]}))
        counts = await seed_from_archive(ctx, archive)
        assert counts["legislation"] == 1
        assert await ctx.store.count(SG_LAW) == counts["chunks"] == 2
        hits = await ctx.store.by_doc_id(SG_LAW, "employment-act-1968")
        assert hits and hits[0]["source_url"] == SSO_URL
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

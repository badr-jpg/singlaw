from datetime import date
from pathlib import Path

import pytest

from app.ingest.chunker import chunk_judgment, chunk_legislation, generic_chunks
from app.ingest.judgment_parser import parse_judgment
from app.ingest.sso_parser import parse_legislation

FIXTURES = Path(__file__).parent / "fixtures"
AS_AT = date(2026, 8, 11)


@pytest.fixture(scope="module")
def ea_chunks():
    doc = parse_legislation((FIXTURES / "employment_act.html").read_text(),
                            source_url="https://sso.agc.gov.sg/Act/EmA1968")
    return chunk_legislation(doc, as_at=AS_AT)


def test_section_level_chunks(ea_chunks):
    citations = [c.citation for c in ea_chunks]
    assert "Employment Act 1968, s 14" in citations
    s14 = next(c for c in ea_chunks if c.citation.endswith("s 14"))
    # whole section in one chunk, subsections intact
    assert "after due inquiry" in s14.text
    assert "at least half" in s14.text


def test_metadata_schema(ea_chunks):
    s14 = next(c for c in ea_chunks if c.citation.endswith("s 14"))
    assert s14.doc_type == "act"
    assert s14.authority_tier == 2
    assert s14.status == "in_force"
    assert s14.sso_version_date == date(2026, 4, 1)
    assert s14.in_force_from == date(1968, 8, 15)
    assert s14.hierarchy_path[0] == "Employment Act 1968"
    assert any("Part 2" in h for h in s14.hierarchy_path)
    assert s14.source_url.endswith("#pr14-")


def test_structural_context(ea_chunks):
    s14 = next(c for c in ea_chunks if c.citation.endswith("s 14"))
    ctx = s14.context
    assert "section 14 of the Employment Act 1968" in ctx
    assert "Part 2" in ctx
    assert "Termination for misconduct" in ctx
    assert "2026-08-11" in ctx  # in-force-as-at statement
    assert "s 2" in ctx  # related provisions: neighbours


def test_oversized_section_splits_at_subsection_boundaries():
    doc = parse_legislation((FIXTURES / "employment_act.html").read_text())
    chunks = chunk_legislation(doc, as_at=AS_AT, max_chars=300)
    parts = [c for c in chunks if c.citation.startswith("Employment Act 1968, s 14")]
    assert len(parts) > 1
    # each split names its subsection range and never cuts inside a subsection
    for c in parts:
        assert "s 14(" in c.citation
    joined = " ".join(c.text for c in parts)
    assert "at least half" in joined


def test_repealed_act_tagged():
    doc = parse_legislation((FIXTURES / "repealed_act.html").read_text())
    chunks = chunk_legislation(doc, as_at=AS_AT)
    assert all(c.status == "repealed" for c in chunks)
    assert all(c.repealed_by == "Act 2 of 2021" for c in chunks)
    assert all(c.in_force_to == date(2021, 3, 1) for c in chunks)


def test_judgment_chunks():
    j = parse_judgment((FIXTURES / "judgment_sgca_2022.html").read_text(),
                       source_url="https://www.judiciary.gov.sg/judgments/2022-sgca-60")
    chunks = chunk_judgment(j, max_chars=100000)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.doc_type == "judgment"
    assert c.authority_tier == 4  # SGCA binds
    assert c.court == "Court of Appeal"
    assert c.citation.startswith("[2022] SGCA 60")
    assert "[2015] SGHC 112" in c.cites
    assert "Tan Ah Kow" in c.context


def test_judgment_chunks_split_on_paragraphs():
    j = parse_judgment((FIXTURES / "judgment_sgca_2022.html").read_text())
    chunks = chunk_judgment(j, max_chars=400)
    assert len(chunks) > 1
    for c in chunks:
        assert "[2022] SGCA 60 at [" in c.citation
    # no paragraph is ever split mid-way: each chunk starts at a para boundary
    nums = [c.citation for c in chunks]
    assert nums == sorted(nums, key=lambda s: int(s.split("at [")[1].split("]")[0]))


def test_generic_chunks_for_practice_directions():
    text = "\n\n".join(f"Paragraph {i}. " + "x " * 120 for i in range(1, 8))
    chunks = generic_chunks(
        text, title="Supreme Court Practice Directions 2021",
        doc_type="practice_direction", source_url="https://example.org/pd",
        max_chars=600,
    )
    assert len(chunks) > 1
    assert all(c.authority_tier == 6 for c in chunks)
    assert all(c.doc_type == "practice_direction" for c in chunks)

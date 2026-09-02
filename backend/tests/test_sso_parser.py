from datetime import date
from pathlib import Path

import pytest

from app.ingest.sso_parser import parse_legislation

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def ea():
    html = (FIXTURES / "employment_act.html").read_text()
    return parse_legislation(html, source_url="https://sso.agc.gov.sg/Act/EmA1968")


@pytest.fixture(scope="module")
def pdpa():
    html = (FIXTURES / "pdpa_plain.html").read_text()
    return parse_legislation(html, source_url="https://sso.agc.gov.sg/Act/PDPA2012")


def test_act_metadata(ea):
    assert ea.title == "Employment Act 1968"
    assert ea.doc_type == "act"
    assert ea.status == "in_force"
    assert ea.sso_version_date == date(2026, 4, 1)
    assert ea.in_force_from == date(1968, 8, 15)
    assert ea.source_url == "https://sso.agc.gov.sg/Act/EmA1968"


def test_sections_extracted(ea):
    numbers = [s.number for s in ea.sections()]
    assert numbers == ["1", "2", "14"]
    s14 = ea.section("14")
    assert s14.heading == "Termination for misconduct"


def test_hierarchy_path(ea):
    s14 = ea.section("14")
    assert s14.part_number == "2"
    assert s14.part_heading == "TERMINATION OF CONTRACT OF SERVICE"


def test_subsection_tree(ea):
    s14 = ea.section("14")
    subs = [c.number for c in s14.children]
    assert subs == ["1", "2", "3"]
    sub1 = s14.children[0]
    paras = [c.number for c in sub1.children]
    assert paras == ["a", "b"]
    # sub-sub: 14(3)(a)(i)-(ii)
    sub3 = s14.children[2]
    para_a = sub3.children[0]
    assert [c.number for c in para_a.children] == ["i", "ii"]


def test_section_text_never_split_mid_provision(ea):
    s14 = ea.section("14")
    full = s14.full_text()
    assert "after due inquiry" in full
    assert "(3)" in full and "at least half" in full


def test_plain_pattern_fallback(pdpa):
    assert pdpa.title == "Personal Data Protection Act 2012"
    numbers = [s.number for s in pdpa.sections()]
    assert numbers == ["1", "13", "16"]
    s13 = pdpa.section("13")
    assert s13.heading == "Consent required"
    assert s13.part_number == "4"
    assert s13.division_heading is not None and "Consent" in s13.division_heading
    assert [c.number for c in s13.children] == ["a", "b"]
    s16 = pdpa.section("16")
    assert [c.number for c in s16.children] == ["1", "2"]


def test_repealed_act():
    html = (FIXTURES / "repealed_act.html").read_text()
    doc = parse_legislation(html, source_url="https://sso.agc.gov.sg/Act/IA1921")
    assert doc.status == "repealed"
    assert doc.repealed_by == "Act 2 of 2021"
    assert doc.in_force_to == date(2021, 3, 1)
    assert [s.number for s in doc.sections()] == ["1", "2"]

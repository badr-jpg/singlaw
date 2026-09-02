from datetime import date
from pathlib import Path

import pytest

from app.ingest.judgment_parser import parse_judgment

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def sgca():
    html = (FIXTURES / "judgment_sgca_2022.html").read_text()
    return parse_judgment(html, source_url="https://www.judiciary.gov.sg/judgments/2022-sgca-60")


def test_metadata(sgca):
    assert sgca.case_name == "Tan Ah Kow v Lim Logistics Pte Ltd"
    assert sgca.neutral_citation == "[2022] SGCA 60"
    assert sgca.court_code == "SGCA"
    assert sgca.court == "Court of Appeal"
    assert sgca.court_level == 5
    assert sgca.decision_date == date(2022, 11, 15)
    assert sgca.coram == ["Sundaresh Menon CJ", "Andrew Phang JCA", "Judith Prakash JCA"]


def test_catchwords(sgca):
    assert len(sgca.catchwords) == 2
    assert "Wrongful dismissal" in sgca.catchwords[0]


def test_paragraph_segmentation(sgca):
    assert [p.number for p in sgca.paragraphs] == [1, 2, 3, 4, 5]
    assert sgca.paragraphs[2].text.startswith("We agree.")


def test_disposition(sgca):
    assert sgca.disposition is not None
    assert "allow the appeal" in sgca.disposition


def test_outbound_citations(sgca):
    assert "[2015] SGHC 112" in sgca.cites
    assert "[2018] SGHC 44" in sgca.cites
    # own citation never listed as an outbound cite
    assert "[2022] SGCA 60" not in sgca.cites


def test_sghc_fixture():
    html = (FIXTURES / "judgment_sghc_2015.html").read_text()
    j = parse_judgment(html, source_url="https://www.judiciary.gov.sg/judgments/2015-sghc-112")
    assert j.neutral_citation == "[2015] SGHC 112"
    assert j.court == "General Division of the High Court"
    assert j.court_level == 3
    assert len(j.paragraphs) == 3

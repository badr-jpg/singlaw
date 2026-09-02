"""Parser for judiciary.gov.sg judgment HTML.

Segments on paragraph numbers ([1], [2], …) since that is the citation unit,
and extracts court, coram, neutral citation, date, catchwords and the
disposition. Class names ("Judg-*") are used as hints with pattern fallbacks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

from app.ingest.citations import NEUTRAL_RX, extract_neutral_citations
from app.ingest.sso_parser import _norm, html_lines, parse_date_str
from app.schemas import COURT_LEVELS

COURT_NAMES: dict[str, str] = {
    "SGCA": "Court of Appeal",
    "SGHC(A)": "Appellate Division of the High Court",
    "SGHC": "General Division of the High Court",
    "SGHC(I)": "Singapore International Commercial Court",
    "SGHCF": "Family Division of the High Court",
    "SGHCR": "High Court (Registrar)",
    "SGDC": "District Court",
    "SGMC": "Magistrate's Court",
}

DECISION_DATE_RX = re.compile(r"Decision Date:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
PARA_START_RX = re.compile(r"^(\d{1,4})\s+(\S.*)$", re.DOTALL)
DISPOSITION_RX = re.compile(
    r"allow(?:ed)? the appeal|dismiss(?:ed)? the appeal|appeal is (?:allowed|dismissed)"
    r"|claim is dismissed|claim is allowed|judgment for the|order accordingly"
    r"|application is (?:granted|dismissed)",
    re.IGNORECASE,
)


@dataclass
class JudgmentPara:
    number: int
    text: str


@dataclass
class Judgment:
    case_name: str
    neutral_citation: str
    court_code: str
    court: str
    court_level: int
    coram: list[str] = field(default_factory=list)
    decision_date: date | None = None
    catchwords: list[str] = field(default_factory=list)
    disposition: str | None = None
    paragraphs: list[JudgmentPara] = field(default_factory=list)
    cites: list[str] = field(default_factory=list)
    source_url: str = ""


def parse_judgment(html: str, source_url: str = "") -> Judgment:
    soup = BeautifulSoup(html, "lxml")
    root = soup.body or soup

    def first_text(*class_names: str) -> str:
        for cn in class_names:
            el = soup.find(class_=cn)
            if el:
                return _norm(el.get_text())
        return ""

    title_text = _norm(soup.title.get_text()) if soup.title else ""
    citation_line = first_text("Judg-Citation") or title_text
    m = NEUTRAL_RX.search(citation_line)
    if not m:
        m = NEUTRAL_RX.search(_norm(soup.get_text(" ")))
    neutral = f"[{m.group(1)}] {m.group(2)} {m.group(3)}" if m else ""
    court_code = m.group(2) if m else ""

    case_name = first_text("Judg-Case-Title")
    if not case_name and title_text:
        case_name = NEUTRAL_RX.sub("", title_text).strip(" -—")

    coram_line = first_text("Judg-Coram")
    coram = [c.strip() for c in re.split(r",\s*|;\s*|\s+and\s+", coram_line) if c.strip()]

    j = Judgment(
        case_name=case_name,
        neutral_citation=neutral,
        court_code=court_code,
        court=COURT_NAMES.get(court_code, first_text("Judg-Court").split("—")[0].strip()),
        court_level=COURT_LEVELS.get(court_code, 1),
        coram=coram,
        source_url=source_url,
    )

    full_text = _norm(soup.get_text(" "))
    if dm := DECISION_DATE_RX.search(full_text):
        j.decision_date = parse_date_str(dm.group(1))

    for el in soup.find_all(class_=re.compile(r"Judg-Catchwords?$")):
        j.catchwords.append(_norm(el.get_text()))

    # paragraph segmentation: numbered leaf blocks, monotonically increasing
    current: JudgmentPara | None = None
    for classes, text in html_lines(root):
        if not text:
            continue
        if any(c.startswith("Judg-") and not c.startswith("Judg-1") for c in classes) \
                and not any(c in ("Judg-No",) for c in classes) \
                and current is None and not PARA_START_RX.match(text):
            continue  # header furniture before the first numbered paragraph
        pm = PARA_START_RX.match(text)
        expected = (j.paragraphs[-1].number + 1) if j.paragraphs else 1
        if pm and pm.group(1).isdigit():
            num = int(pm.group(1))
            plausible = (expected <= num <= expected + 5) if j.paragraphs else num <= 3
            if plausible:
                current = JudgmentPara(number=num, text=pm.group(2).strip())
                j.paragraphs.append(current)
                continue
        if current is not None:
            current.text = f"{current.text} {text}".strip()

    own = j.neutral_citation
    j.cites = [c for c in extract_neutral_citations(
        " ".join(p.text for p in j.paragraphs)) if c != own]

    for p in reversed(j.paragraphs[-3:] if len(j.paragraphs) >= 3 else j.paragraphs):
        if DISPOSITION_RX.search(p.text):
            j.disposition = p.text
            break

    return j

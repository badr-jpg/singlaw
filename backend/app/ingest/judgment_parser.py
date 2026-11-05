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
    "SGCA(I)": "Court of Appeal (international commercial)",
    "SGHC(A)": "Appellate Division of the High Court",
    "SGHC": "General Division of the High Court",
    "SGHC(I)": "Singapore International Commercial Court",
    "SGHCF": "Family Division of the High Court",
    "SGHCR": "High Court (Registrar)",
    "SGDC": "District Court",
    "SGMC": "Magistrate's Court",
}

# eLitigation URL slugs drop the brackets: 2026_SGHCA_26 is [2026] SGHC(A) 26
SLUG_COURT_CODES: dict[str, str] = {
    "SGHCA": "SGHC(A)", "SGHCI": "SGHC(I)", "SGCAI": "SGCA(I)"}

DECISION_DATE_RX = re.compile(r"Decision Date:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
PARA_START_RX = re.compile(r"^(\d{1,4})\s+(\S.*)$", re.DOTALL)
DISPOSITION_RX = re.compile(
    r"allow(?:ed)? the appeal|dismiss(?:ed)? the appeal|appeal is (?:allowed|dismissed)"
    r"|claim is dismissed|claim is allowed|judgment for the|order accordingly"
    r"|application is (?:granted|dismissed)"
    r"|\bappeals?\s+(?:allowed|dismissed)\b"
    r"|\b(?:I|we)\s+(?:therefore\s+|accordingly\s+|would\s+)?"
    r"(?:allow|dismiss|grant|refuse|set aside|affirm|uphold|make the following orders)\b"
    r"|\b(?:is|are)\s+(?:allowed|dismissed|granted|refused)(?:\s+in part)?\b",
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
    # False when the source has no paragraph numbers (pre-2003 eLitigation
    # pages): `number` is then a sequence index, never a citable pinpoint
    numbered: bool = True


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


# ---------------------------------------------------------------- eLitigation

_ELIT_SKIP = re.compile(r"^Judg-(Sign|Author|Date|Hearing|Lawyers|EOF)")
_ELIT_PARA_RX = re.compile(r"^(\d{1,4})\.?[\s\u2003]+(\S.*)$", re.DOTALL)
_LEGACY_BLOCKS = ("p", "blockquote", "table", "div", "ol", "ul", "pre", "font", "i")
_SMALL_WORDS = {"v", "and", "of", "the", "in", "for", "on", "at", "to", "by", "an", "a"}


def _case_title(raw: str) -> str:
    """eLitigation lists titles in capitals; render them readably."""
    letters = [c for w in raw.split() if w != "v" for c in w if c.isalpha()]
    if not letters or any(c.islower() for c in letters):
        return raw.strip()  # already mixed case (the " v " connector aside)
    words = raw.strip().split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        out.append(lw if i and lw in _SMALL_WORDS else w[:1].upper() + w[1:].lower())
    return " ".join(out)


def parse_elitigation_judgment(
    html: str, entry: dict | None = None, source_url: str = "",
) -> Judgment:
    """Parse an eLitigation judgment page (www.elitigation.sg/gd/s/<slug>).

    Paragraphs are `Judg-1` blocks whose text starts with the paragraph number;
    quotes and lists continue the current paragraph; headings are carried into
    the next paragraph. Footnotes, counsel lines and the signature block are not
    paragraph text. `entry` is the listing row (citation, title, decision date,
    catchwords), which is more reliable than the page header.
    """
    entry = entry or {}
    soup = BeautifulSoup(html, "lxml")
    for sup in soup.find_all("sup"):
        sup.decompose()  # footnote reference markers

    neutral = entry.get("citation") or ""
    if not neutral:
        m = NEUTRAL_RX.search(_norm(soup.title.get_text() if soup.title else ""))
        m = m or NEUTRAL_RX.search(_norm(soup.get_text(" ")))
        neutral = f"[{m.group(1)}] {m.group(2)} {m.group(3)}" if m else ""
    m = NEUTRAL_RX.search(neutral)
    court_code = SLUG_COURT_CODES.get(m.group(2), m.group(2)) if m else ""

    coram: list[str] = []
    for el in soup.find_all(class_=re.compile(r"^Judg-Sign")):
        lines = [ln.strip() for ln in el.get_text("\n").split("\n") if ln.strip()]
        if lines:
            coram.append(lines[0])
    if not coram:
        for el in soup.find_all(class_=re.compile(r"^Judg-Author")):
            coram.append(_norm(el.get_text()).rstrip(":").strip())

    j = Judgment(
        case_name=_case_title(entry.get("title", "")),
        neutral_citation=neutral,
        court_code=court_code,
        court=COURT_NAMES.get(court_code, court_code),
        court_level=COURT_LEVELS.get(court_code, 1),
        coram=[c for c in coram if c],
        source_url=source_url,
    )
    if entry.get("decision_date"):
        try:
            j.decision_date = date.fromisoformat(entry["decision_date"])
        except ValueError:
            pass
    if j.decision_date is None:
        for el in soup.find_all(class_=re.compile(r"^Judg-Date")):
            if d := parse_date_str(_norm(el.get_text())):
                j.decision_date = d
                break

    j.catchwords = list(entry.get("catchwords") or []) or [
        _norm(el.get_text()).strip("[] ") for el in soup.find_all(class_="catchwords")
        if _norm(el.get_text())]

    matched: set[int] = set()
    current: JudgmentPara | None = None
    pending_heading: str | None = None
    for el in soup.find_all(class_=re.compile(r"^Judg-")):
        if any(id(parent) in matched for parent in el.parents):
            continue
        matched.add(id(el))
        cls = " ".join(el.get("class") or [])
        if _ELIT_SKIP.match(cls):
            continue
        text = _norm(el.get_text(" "))
        if not text:
            continue
        if cls.startswith("Judg-Heading"):
            pending_heading = text
            continue
        pm = _ELIT_PARA_RX.match(text) if cls.startswith("Judg-1") else None
        if pm:
            num = int(pm.group(1))
            last = j.paragraphs[-1].number if j.paragraphs else 0
            # Judg-1 blocks only hold paragraphs, so accept any forward step:
            # source pages occasionally skip numbers (one jumps 163 -> 195)
            if last < num <= last + 50:
                body = pm.group(2).strip()
                if pending_heading:
                    body = f"[{pending_heading}] {body}"
                    pending_heading = None
                current = JudgmentPara(number=num, text=body)
                j.paragraphs.append(current)
                continue
        if current is not None:
            current.text = f"{current.text} {text}".strip()

    if not j.paragraphs:
        _parse_legacy_body(soup, j)
    if not j.coram:
        j.coram = _legacy_coram(soup)

    j.cites = [c for c in extract_neutral_citations(
        " ".join(p.text for p in j.paragraphs)) if c != j.neutral_citation]
    for para in reversed(j.paragraphs[-3:]):
        if DISPOSITION_RX.search(para.text):
            j.disposition = para.text
            break
    return j


def _legacy_coram(soup: BeautifulSoup) -> list[str]:
    """Older pages give the coram as a row of the header info table."""
    for row in soup.select("#info-table tr"):
        label = row.find(class_="txt-label")
        if label and _norm(label.get_text()).lower() == "coram":
            body = row.find(class_="txt-body")
            text = _norm(body.get_text(" ")) if body else ""
            return [c.strip() for c in re.split(r";", text) if c.strip()]
    return []


def _parse_legacy_body(soup: BeautifulSoup, j: Judgment) -> None:
    """Pre-2004 pages have no Judg-* classes: the body is the run of blocks
    after the header table in div.contentsOfFile. Paragraphs are numbered
    "1 text" or "1. text" in most; the oldest carry no numbers at all, so each
    top-level paragraph block becomes one sequence-numbered paragraph and the
    judgment is flagged as unnumbered."""
    container = soup.find(class_="contentsOfFile")
    table = container.find(id="info-table") if container else None
    if table is None:
        return
    blocks = []
    for el in table.find_next_siblings():
        if el.name not in _LEGACY_BLOCKS and el.name not in ("b", "strong", "h3", "h4"):
            continue
        if "txt-body" in (el.get("class") or []):
            continue  # catchwords box (catchwords come from the listing)
        text = _norm(el.get_text(" "))
        if text:
            blocks.append((el.name, text))

    numbered = [b for b in blocks if b[0] == "p" and _ELIT_PARA_RX.match(b[1])]
    current: JudgmentPara | None = None
    pending_heading: str | None = None
    if len(numbered) >= 2:
        for name, text in blocks:
            pm = _ELIT_PARA_RX.match(text) if name == "p" else None
            if pm:
                num = int(pm.group(1))
                last = j.paragraphs[-1].number if j.paragraphs else 0
                if last < num <= last + 50:
                    body = pm.group(2).strip()
                    if pending_heading:
                        body = f"[{pending_heading}] {body}"
                        pending_heading = None
                    current = JudgmentPara(number=num, text=body)
                    j.paragraphs.append(current)
                    continue
            is_heading = name in ("b", "strong", "h3", "h4") or (
                current is not None and name == "p" and len(text) < 80
                and not text.endswith((".", ":", ";")))
            if is_heading:
                pending_heading = text
                continue
            if current is None:
                continue  # preamble before paragraph 1 ("Cur Adv Vult" etc.)
            current.text = f"{current.text} {text}".strip()
        return

    j.numbered = False
    for name, text in blocks:
        if name == "p" or current is None:
            current = JudgmentPara(number=len(j.paragraphs) + 1, text=text)
            j.paragraphs.append(current)
        else:  # quotes, tables and lists belong to the paragraph before them
            current.text = f"{current.text} {text}".strip()

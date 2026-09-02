"""Structure-aware parser for Singapore Statutes Online legislation HTML.

Legislation is a tree (Act → Part → Division → Section → Subsection →
Paragraph → Sub-paragraph) and SSO serves structured HTML. This parser is
deliberately pattern-based: it uses SSO's known CSS classes as *hints* but
falls back to provision-number patterns over linearized text, so class-name
drift on SSO's side degrades gracefully instead of breaking. Unparsed
residue is kept on the document for logging, never silently dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from bs4 import BeautifulSoup, NavigableString, Tag

# ---------------------------------------------------------------- HTML → lines

_BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
    "table", "tr", "td", "section", "article", "blockquote",
}
# spans that SSO renders as standalone structural lines
_SPAN_LINE_CLASSES = {"partNo", "partHdr", "prov1Hdr", "actHd"}


def _classes(tag: Tag) -> set[str]:
    return set(tag.get("class") or [])


def _is_line_block(tag: Tag) -> bool:
    if tag.name in _BLOCK_TAGS:
        return True
    return tag.name == "span" and bool(_classes(tag) & _SPAN_LINE_CLASSES)


def _norm(text: str) -> str:
    text = text.replace(" ", " ").replace("–", "—")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def html_lines(root: Tag) -> list[tuple[set[str], str]]:
    """Linearize HTML into (classes, text) lines, one per leaf block, with
    inline content joined so "<strong>14.</strong>—(1) …" stays one line."""
    out: list[tuple[set[str], str]] = []

    def emit(el: Tag) -> None:
        buf: list[str] = []

        def flush() -> None:
            text = _norm("".join(buf))
            buf.clear()
            if text:
                out.append((_classes(el), text))

        for child in el.children:
            if isinstance(child, Tag) and _is_line_block(child):
                flush()
                emit(child)
            elif isinstance(child, Tag):
                buf.append(child.get_text())
            elif isinstance(child, NavigableString):
                buf.append(str(child))
        flush()

    emit(root)
    return out


# ---------------------------------------------------------------- data model


@dataclass
class Provision:
    kind: str  # "section" | "subsection" | "paragraph" | "subparagraph"
    number: str
    heading: str = ""
    text: str = ""
    children: list[Provision] = field(default_factory=list)
    # populated on sections only
    part_number: str | None = None
    part_heading: str | None = None
    division_number: str | None = None
    division_heading: str | None = None

    def marker(self) -> str:
        return f"{self.number}." if self.kind == "section" else f"({self.number})"

    def render(self) -> str:
        own = f"{self.marker()} {self.text}".strip()
        return "\n".join([own] + [c.render() for c in self.children])

    def full_text(self) -> str:
        return self.render()

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class LegisDoc:
    title: str
    doc_type: str  # "act" | "subsidiary_legislation"
    status: str = "in_force"  # | "repealed" | "spent" | "not_yet_commenced"
    source_url: str = ""
    long_title: str = ""
    sso_version_date: date | None = None
    in_force_from: date | None = None
    in_force_to: date | None = None
    repealed_by: str | None = None
    body: list[Provision] = field(default_factory=list)  # sections, in order
    unparsed: list[str] = field(default_factory=list)

    def sections(self) -> list[Provision]:
        return self.body

    def section(self, number: str) -> Provision | None:
        for s in self.body:
            if s.number == number:
                return s
        return None


# ---------------------------------------------------------------- patterns

_MONTHS = "|".join(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)
DATE_RX = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")

VERSION_RX = re.compile(r"Current version as at\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
COMMENCE_RX = re.compile(r"Date of commencement:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
REPEALED_BY_RX = re.compile(
    r"Repealed by\s+((?:Act|S)\s+\d+(?:\s+of\s+\d{4}|/\d{4}))"
    r"(?:\s+with effect from\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4}))?"
)
PART_RX = re.compile(r"^PART\s+([0-9]+[A-Z]?|[IVXLC]+)$")
DIVISION_RX = re.compile(r"^Division\s+(\d+[A-Z]?)\s*—\s*(.+)$")
SEC_WITH_SUB_RX = re.compile(r"^(\d+[A-Z]{0,2})\.\s*—\s*\((\d+[A-Z]{0,2})\)\s*(.*)$")
SEC_SIMPLE_RX = re.compile(r"^(\d+[A-Z]{0,2})\.\s+(\S.*)$")
PAREN_RX = re.compile(r"^\(([0-9A-Za-z]{1,4})\)\s*(.*)$")
LONG_TITLE_RX = re.compile(r"^An Act\b|^An? (?:Order|Regulations?|Rules?)\b")

_ROMAN_CHARS = set("ivxlcdm")
_SL_TITLE_RX = re.compile(r"\b(Regulations?|Rules?|Order|Notification)\b")


def parse_date_str(s: str) -> date | None:
    m = DATE_RX.search(s)
    if not m:
        return None
    day, mon, year = m.groups()
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(f"{int(day)} {mon} {year}", fmt).date()
        except ValueError:
            continue
    return None


def _next_letter(s: str) -> str:
    """aa-style successor: a→b, h→i, z→aa, az→ba."""
    chars = list(s)
    i = len(chars) - 1
    while i >= 0:
        if chars[i] != "z":
            chars[i] = chr(ord(chars[i]) + 1)
            return "".join(chars)
        chars[i] = "a"
        i -= 1
    return "a" + "".join(chars)


def _heading_like(text: str) -> bool:
    if not text or len(text) > 90:
        return False
    if text[-1] in ".;:,—":
        return False
    if not text[0].isupper():
        return False
    if PAREN_RX.match(text) or SEC_SIMPLE_RX.match(text) or SEC_WITH_SUB_RX.match(text):
        return False
    return True


# ---------------------------------------------------------------- parser


def infer_doc_type(title: str, source_url: str) -> str:
    if "/SL/" in source_url or "/SL-" in source_url:
        return "subsidiary_legislation"
    if _SL_TITLE_RX.search(title) and " Act " not in f" {title} ":
        return "subsidiary_legislation"
    return "act"


def parse_legislation(
    html: str, source_url: str = "", doc_type: str | None = None
) -> LegisDoc:
    soup = BeautifulSoup(html, "lxml")
    root = soup.body or soup

    # ---- metadata from targeted hints, tolerant of missing classes ----
    title = ""
    el = soup.find(class_="actHd") or soup.find(class_="legis-title") or soup.find("h1")
    if el:
        title = _norm(el.get_text())
    if not title and soup.title:
        title = _norm(soup.title.get_text()).split(" - ")[0]

    full_text = _norm(soup.get_text(" "))
    doc = LegisDoc(title=title, doc_type=doc_type or infer_doc_type(title, source_url),
                   source_url=source_url)

    if m := VERSION_RX.search(full_text):
        doc.sso_version_date = parse_date_str(m.group(1))
    if m := COMMENCE_RX.search(full_text):
        doc.in_force_from = parse_date_str(m.group(1))
    if m := REPEALED_BY_RX.search(full_text):
        doc.status = "repealed"
        doc.repealed_by = m.group(1)
        if m.group(2):
            doc.in_force_to = parse_date_str(m.group(2))
    elif re.search(r"\bREPEALED\b", full_text):
        doc.status = "repealed"

    # ---- body: state machine over linearized lines ----
    lines = html_lines(root)

    pending_part: str | None = None       # part number awaiting its heading
    current_part: tuple[str, str] | None = None
    current_division: tuple[str, str] | None = None
    pending_heading: str | None = None    # candidate section heading
    section: Provision | None = None
    stack: list[Provision] = []           # open provisions, section first

    def open_section(number: str, first_text: str, heading: str | None) -> Provision:
        nonlocal section
        section = Provision(kind="section", number=number, heading=heading or "",
                            text=first_text)
        if current_part:
            section.part_number, section.part_heading = current_part
        if current_division:
            section.division_number, section.division_heading = current_division
        doc.body.append(section)
        stack.clear()
        stack.append(section)
        return section

    def attach(kind: str, number: str, text: str) -> None:
        node = Provision(kind=kind, number=number, text=text)
        keep = {"subsection": {"section"},
                "paragraph": {"subsection", "section"},
                "subparagraph": {"paragraph"}}[kind]
        while stack and stack[-1].kind not in keep:
            stack.pop()
        if not stack:
            doc.unparsed.append(f"({number}) {text}")
            return
        stack[-1].children.append(node)
        stack.append(node)

    def classify_paren(token: str) -> str:
        if token[0].isdigit():
            return "subsection"
        open_para = next((p for p in reversed(stack) if p.kind == "paragraph"), None)
        is_roman = all(c in _ROMAN_CHARS for c in token.lower()) and token == token.lower()
        if is_roman and open_para is not None and token != _next_letter(open_para.number):
            return "subparagraph"
        return "paragraph"

    def flush_pending_heading() -> None:
        nonlocal pending_heading
        if pending_heading is None:
            return
        if stack:
            stack[-1].text = f"{stack[-1].text} {pending_heading}".strip()
        else:
            doc.unparsed.append(pending_heading)
        pending_heading = None

    for classes, text in lines:
        if not text or text == title:
            continue
        # metadata lines already captured above
        if (VERSION_RX.search(text) or COMMENCE_RX.search(text)
                or REPEALED_BY_RX.search(text) or text == "REPEALED"):
            continue
        if LONG_TITLE_RX.match(text) and not doc.long_title:
            doc.long_title = text
            continue

        # -- parts / divisions --
        if "partNo" in classes or PART_RX.match(text):
            m = PART_RX.match(text)
            pending_part = m.group(1) if m else text
            current_division = None
            pending_heading = None
            continue
        if pending_part is not None:
            current_part = (pending_part, text)
            pending_part = None
            continue
        if m := DIVISION_RX.match(text):
            current_division = (m.group(1), m.group(2).strip())
            pending_heading = None
            continue

        # -- explicit section heading (structured mode) --
        if "prov1Hdr" in classes:
            pending_heading = text
            continue

        # -- section starts --
        if m := SEC_WITH_SUB_RX.match(text):
            num, subnum, rest = m.groups()
            open_section(num, "", pending_heading)
            pending_heading = None
            attach("subsection", subnum, rest)
            continue
        if m := SEC_SIMPLE_RX.match(text):
            open_section(m.group(1), m.group(2), pending_heading)
            pending_heading = None
            continue

        # -- subsections / paragraphs / sub-paragraphs --
        if (m := PAREN_RX.match(text)) and section is not None:
            flush_pending_heading()
            token, rest = m.group(1), m.group(2)
            attach(classify_paren(token), token, rest)
            continue

        # -- plain-mode heading candidate, else continuation text --
        if _heading_like(text):
            flush_pending_heading()
            pending_heading = text
            continue
        flush_pending_heading()
        if stack:
            stack[-1].text = f"{stack[-1].text} {text}".strip()
        else:
            doc.unparsed.append(text)

    return doc

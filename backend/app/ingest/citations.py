"""Citation extraction, the citation graph, and the treatment pass.

Neutral citations look like "[2022] SGCA 60"; statutory references like
"s 14(2) of the Employment Act 1968". The graph is a directed edge set
(citing judgment → cited authority) persisted in SQLite by the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NEUTRAL_RX = re.compile(r"\[(\d{4})\]\s+(SG[A-Z]{2,6}(?:\([A-Z]\))?)\s+(\d{1,4})")

# "Employment Act 1968", "Personal Data Protection Act 2012"
_ACT_NAME = r"[A-Z][A-Za-z'’]*(?:\s+(?:[A-Z][A-Za-z'’]*|of|and|for|to|the))*?\s+Act\s+\d{4}"
ACT_RX = re.compile(rf"\b({_ACT_NAME})\b")
# "s 14(2) of the Employment Act 1968" / "section 13 of the Employment Claims Act 2016"
SECTION_REF_RX = re.compile(
    rf"\bs(?:ection)?\s+(\d+[A-Z]{{0,2}}(?:\(\d+[A-Z]?\))*(?:\([a-z]+\))*)\s+of\s+the\s+({_ACT_NAME})\b"
)


def extract_neutral_citations(text: str) -> list[str]:
    """Order-preserving, deduplicated neutral citations found in text."""
    seen: dict[str, None] = {}
    for m in NEUTRAL_RX.finditer(text):
        cite = f"[{m.group(1)}] {m.group(2)} {m.group(3)}"
        seen.setdefault(cite, None)
    return list(seen)


def extract_statute_refs(text: str) -> list[str]:
    """Statutory references as canonical citations: "Employment Act 1968, s 14(2)".

    Bare Act mentions (no section) yield just the Act citation.
    """
    seen: dict[str, None] = {}
    sectioned_spans: list[tuple[int, int]] = []
    for m in SECTION_REF_RX.finditer(text):
        seen.setdefault(f"{m.group(2)}, s {m.group(1)}", None)
        sectioned_spans.append(m.span(2))
    for m in ACT_RX.finditer(text):
        if any(s <= m.start(1) < e for s, e in sectioned_spans):
            continue  # already captured with its section
        seen.setdefault(m.group(1), None)
    return list(seen)


# --- treatment pass -------------------------------------------------------

# Conservative by design (DECISIONS.md #9): explicit language only.
OVERRULE_RX = re.compile(
    r"\b(?:is|are|be|stands?)\s+overruled\b"
    r"|\boverrule[sd]?\b"
    r"|\bno longer good law\b"
    r"|\bwrongly decided\b"
    r"|\bcannot stand\b",
    re.IGNORECASE,
)
DISTINGUISH_RX = re.compile(r"\bdistinguish(?:ed|able|ing)?\b", re.IGNORECASE)

# window of characters around a citation in which treatment language counts
_WINDOW = 300


@dataclass
class CitationEdge:
    citing: str          # neutral citation of the citing judgment
    cited: str           # neutral citation or statute citation cited
    kind: str            # "case" | "statute"
    treatment_hint: str  # "overruled" | "distinguished" | "neutral"
    paragraph: int | None = None


def edges_from_paragraphs(
    own_citation: str,
    paragraphs: list[tuple[int, str]],
) -> list[CitationEdge]:
    """Extract outbound edges with local treatment hints from judgment text.

    A hint is attached when overruling/distinguishing language appears within
    ±300 chars of the citation in the same paragraph — proximity, not global
    paragraph mood, so one paragraph overruling X and citing Y neutrally does
    not smear "overruled" onto Y.
    """
    edges: list[CitationEdge] = []
    seen: set[tuple[str, str]] = set()
    for num, text in paragraphs:
        for m in NEUTRAL_RX.finditer(text):
            cited = f"[{m.group(1)}] {m.group(2)} {m.group(3)}"
            if cited == own_citation:
                continue
            lo = max(0, m.start() - _WINDOW)
            hi = min(len(text), m.end() + _WINDOW)
            window = text[lo:hi]
            if OVERRULE_RX.search(window):
                hint = "overruled"
            elif DISTINGUISH_RX.search(window):
                hint = "distinguished"
            else:
                hint = "neutral"
            key = (cited, hint)
            if key in seen:
                continue
            seen.add(key)
            edges.append(CitationEdge(own_citation, cited, "case", hint, num))
        for ref in extract_statute_refs(text):
            key = (ref, "statute")
            if key in seen:
                continue
            seen.add(key)
            edges.append(CitationEdge(own_citation, ref, "statute", "neutral", num))
    return edges


def resolve_treatment(
    hints: list[tuple[str, int, str]],
) -> str:
    """Fold (hint, citing_court_level, cited_court_level→ via caller filter) hints
    into a single treatment for a cited case.

    Callers pass only hints from judgments *later in time* than the cited case.
    "overruled" requires the citing court to be same-or-higher level; otherwise
    the hint degrades to "distinguished"/"unknown". Precedence:
    overruled > distinguished > good.
    """
    result = "unknown"
    for hint, citing_level, cited_level in hints:
        if hint == "overruled" and citing_level >= cited_level:
            return "overruled"
        if hint == "distinguished":
            result = "distinguished"
        elif hint == "neutral" and result == "unknown":
            result = "good"
    return result

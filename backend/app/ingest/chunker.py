"""Tree → chunks, and the structural context builder (contextual retrieval).

Legislation chunks at section level, splitting oversized sections only at
subsection boundaries — never mid-provision. Judgments chunk on paragraph
number groups, since [n] is the citation unit. Context strings are derived
deterministically from the parse tree (spec §2.3); no LLM involved.
"""
from __future__ import annotations

import re
from datetime import date

from app.ingest.judgment_parser import Judgment
from app.ingest.sso_parser import LegisDoc, Provision
from app.schemas import (
    BINDING_COURTS,
    TIER_ACT,
    TIER_BINDING_JUDGMENT,
    TIER_CONSTITUTION,
    TIER_GUIDANCE,
    TIER_LOWER_COURT,
    TIER_SL,
    ChunkPayload,
)

DEFAULT_MAX_CHARS = 4000


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def legislation_tier(doc: LegisDoc) -> int:
    if "constitution of the republic of singapore" in doc.title.lower():
        return TIER_CONSTITUTION
    return TIER_SL if doc.doc_type == "subsidiary_legislation" else TIER_ACT


def _status_sentence(doc: LegisDoc, as_at: date) -> str:
    if doc.status == "repealed":
        by = f" by {doc.repealed_by}" if doc.repealed_by else ""
        eff = f" with effect from {doc.in_force_to.isoformat()}" if doc.in_force_to else ""
        return f"It was repealed{by}{eff} and is no longer in force as at {as_at.isoformat()}."
    if doc.status == "not_yet_commenced":
        return f"It has not yet commenced as at {as_at.isoformat()}."
    if doc.status == "spent":
        return f"It is spent as at {as_at.isoformat()}."
    return f"It is in force as at {as_at.isoformat()}."


def _section_context(
    doc: LegisDoc, section: Provision, label: str, as_at: date,
    related: list[str],
) -> str:
    parts = [f"This is section {label} of the {doc.title} (Singapore)"]
    if section.part_number:
        parts.append(f", within Part {section.part_number} ({section.part_heading})")
    if section.division_number:
        parts.append(
            f", Division {section.division_number} ({section.division_heading})")
    sent = ["".join(parts) + "."]
    if section.heading:
        sent.append(f'The section is titled "{section.heading}".')
    sent.append(_status_sentence(doc, as_at))
    if related:
        sent.append("Related provisions: " + ", ".join(related) + ".")
    return " ".join(sent)


def _hierarchy(doc: LegisDoc, section: Provision) -> list[str]:
    path = [doc.title]
    if section.part_number:
        path.append(f"Part {section.part_number} — {section.part_heading}")
    if section.division_number:
        path.append(f"Division {section.division_number} — {section.division_heading}")
    head = f" — {section.heading}" if section.heading else ""
    path.append(f"Section {section.number}{head}")
    return path


def _base_payload(doc: LegisDoc, as_at: date) -> dict:
    return dict(
        collection="sg_law",
        doc_type=doc.doc_type,
        authority_tier=legislation_tier(doc),
        status=doc.status,
        in_force_from=doc.in_force_from,
        in_force_to=doc.in_force_to,
        repealed_by=doc.repealed_by,
        sso_version_date=doc.sso_version_date,
        title=doc.title,
    )


def chunk_legislation(
    doc: LegisDoc, *, as_at: date | None = None, max_chars: int = DEFAULT_MAX_CHARS
) -> list[ChunkPayload]:
    as_at = as_at or date.today()
    doc_id = slugify(doc.title)
    sections = doc.sections()
    chunks: list[ChunkPayload] = []

    for i, sec in enumerate(sections):
        neighbours = []
        if i > 0:
            neighbours.append(f"s {sections[i - 1].number}")
        if i + 1 < len(sections):
            neighbours.append(f"s {sections[i + 1].number}")
        anchor_url = f"{doc.source_url}#pr{sec.number}-" if doc.source_url else ""
        common = dict(
            _base_payload(doc, as_at),
            doc_id=doc_id,
            hierarchy_path=_hierarchy(doc, sec),
            source_url=anchor_url,
        )

        rendered = sec.render()
        if len(rendered) <= max_chars or not sec.children:
            chunks.append(ChunkPayload(
                chunk_id=f"{doc_id}:s{sec.number}",
                citation=f"{doc.title}, s {sec.number}",
                text=rendered,
                context=_section_context(doc, sec, sec.number, as_at, neighbours),
                **common,
            ))
            continue

        # oversized: split at subsection boundaries, never mid-provision
        header = f"{sec.number}. {sec.text}".strip()
        groups: list[list[Provision]] = []
        current: list[Provision] = []
        used = len(header)
        for sub in sec.children:
            r = len(sub.render())
            if current and used + r > max_chars:
                groups.append(current)
                current, used = [], len(header)
            current.append(sub)
            used += r
        if current:
            groups.append(current)

        all_sub_labels = [f"s {sec.number}({c.number})" for c in sec.children]
        for group in groups:
            lo, hi = group[0].number, group[-1].number
            rng = f"({lo})" if lo == hi else f"({lo})–({hi})"
            label = f"{sec.number}{rng}"
            in_group = {f"s {sec.number}({g.number})" for g in group}
            related = [x for x in all_sub_labels if x not in in_group] + neighbours
            text = "\n".join([header] + [g.render() for g in group])
            chunks.append(ChunkPayload(
                chunk_id=f"{doc_id}:s{sec.number}{rng}",
                citation=f"{doc.title}, s {label}",
                text=text,
                context=_section_context(doc, sec, label, as_at, related),
                **common,
            ))
    return chunks


# --------------------------------------------------------------- judgments


def judgment_tier(court_code: str) -> int:
    return TIER_BINDING_JUDGMENT if court_code in BINDING_COURTS else TIER_LOWER_COURT


def _judgment_context(j: Judgment, para_lo: int, para_hi: int) -> str:
    rng = f"[{para_lo}]" if para_lo == para_hi else f"[{para_lo}]–[{para_hi}]"
    d = j.decision_date
    decided = f", decided {d.day} {d:%B %Y}" if d else ""  # %-d is not portable to Windows
    where = (f"paragraph{'s' if para_lo != para_hi else ''} {rng}" if j.numbered
             else "an extract")  # unnumbered source: no pinpoint to give
    sent = [
        f"This is {where} of the judgment in "
        f"{j.case_name} {j.neutral_citation} ({j.court}{decided})."
    ]
    if j.catchwords:
        sent.append("Catchwords: " + "; ".join(j.catchwords) + ".")
    return " ".join(sent)


def chunk_judgment(
    j: Judgment, *, max_chars: int = DEFAULT_MAX_CHARS
) -> list[ChunkPayload]:
    doc_id = slugify(f"{j.neutral_citation} {j.case_name}")
    groups: list[list] = []
    current: list = []
    used = 0
    label = (lambda p: f"[{p.number}] {p.text}") if j.numbered else (lambda p: p.text)
    for p in j.paragraphs:
        text = label(p)
        if current and used + len(text) > max_chars:
            groups.append(current)
            current, used = [], 0
        current.append(p)
        used += len(text)
    if current:
        groups.append(current)

    common = dict(
        collection="sg_law",
        doc_type="judgment",
        authority_tier=judgment_tier(j.court_code),
        status="in_force",
        court=j.court,
        court_level=j.court_level,
        decision_date=j.decision_date,
        source_url=j.source_url,
        title=f"{j.case_name} {j.neutral_citation}",
        doc_id=doc_id,
        cites=j.cites,
    )
    single = len(groups) == 1
    chunks = []
    for i, group in enumerate(groups, start=1):
        lo, hi = group[0].number, group[-1].number
        rng = f"[{lo}]" if lo == hi else f"[{lo}]–[{hi}]"
        if j.numbered:
            citation = j.neutral_citation if single else f"{j.neutral_citation} at {rng}"
            where, chunk_id = f"Paragraphs {rng}", f"{doc_id}:para{lo}-{hi}"
        else:  # never invent a pinpoint the source does not print
            citation = j.neutral_citation
            where, chunk_id = f"Part {i} of {len(groups)}", f"{doc_id}:part{i}"
        hierarchy = [f"{j.case_name} {j.neutral_citation}", j.court, where]
        chunks.append(ChunkPayload(
            chunk_id=chunk_id,
            citation=citation,
            text="\n".join(label(p) for p in group),
            context=_judgment_context(j, lo, hi),
            hierarchy_path=hierarchy,
            **common,
        ))
    return chunks


# --------------------------------------------------------------- generic


def generic_chunks(
    text: str, *, title: str, doc_type: str, source_url: str = "",
    max_chars: int = DEFAULT_MAX_CHARS, collection: str = "sg_law",
    user_id: str | None = None, doc_id: str | None = None,
    context_fn=None,
) -> list[ChunkPayload]:
    """Paragraph-boundary chunking for material without provision structure
    (practice directions, phase-2 guidance, user uploads)."""
    doc_id = doc_id or slugify(title)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    groups: list[list[str]] = []
    current: list[str] = []
    used = 0
    for p in paras:
        if current and used + len(p) > max_chars:
            groups.append(current)
            current, used = [], 0
        current.append(p)
        used += len(p)
    if current:
        groups.append(current)

    kind_label = {
        "practice_direction": "a procedural practice direction",
        "guidance": "regulatory guidance (non-binding)",
        "user_document": "a document uploaded by the user; it is the user's "
                         "factual situation, not legal authority",
    }.get(doc_type, "supporting material")
    chunks = []
    for idx, group in enumerate(groups, start=1):
        body = "\n\n".join(group)
        default_ctx = (
            f"This is part {idx} of {len(groups)} of {title} (Singapore), {kind_label}."
        )
        chunks.append(ChunkPayload(
            chunk_id=f"{doc_id}:part{idx}",
            doc_id=doc_id,
            collection=collection,  # type: ignore[arg-type]
            user_id=user_id,
            citation=f"{title} (part {idx})" if len(groups) > 1 else title,
            text=body,
            context=context_fn(idx, body) if context_fn else default_ctx,
            title=title,
            doc_type=doc_type,  # type: ignore[arg-type]
            authority_tier=TIER_GUIDANCE,
            status="in_force" if doc_type != "user_document" else "n_a",
            hierarchy_path=[title, f"Part {idx}"],
            source_url=source_url,
        ))
    return chunks

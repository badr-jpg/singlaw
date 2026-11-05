"""Legislation corpus: the Hugging Face copy of Singapore Statutes Online.

Dataset: Kaidon-Ng/singapore-statutes ("LawBot Project", 2026), 535 Acts and
1,782 pieces of subsidiary legislation parsed from SSO PDFs into one row per
section. Reused under clause 13 of the SSO Terms of Use, which permits
reproducing Singapore legislation provided the material states that it is
subject to Singapore Government copyright and that the latest version can be
checked on SSO (both are in AGC_ATTRIBUTION, shown with every answer).
Nothing here contacts SSO.

Input: data/corpus/sso_statutes/sections.jsonl, converted from the dataset's
sections.parquet by scripts/prepare_sso_statutes.py. Documented fields:
doc_name, doc_type, parent_act, section_title, part, division, pages, text.

One chunk per section (the citation unit, like chunk_legislation). A section
longer than max_chars is split at subsection boundaries "(2)", "(3)" …, and
only if a single subsection is still too long, at sentence boundaries.
Chunk ids are deterministic: <doc_id>:s<number>[.<k>].

Each Act's first row ("Unsectioned") is its cover page and table of
contents. It is not indexed (it would match every question about the Act),
but two facts are read from it: the full Act name (the dataset truncates
long names at 50 characters) and the consolidation date ("version in force
from 9/12/2024"), stored as sso_version_date. Schedules ("FIRST SCHEDULE",
"FIRST SCHEDULE — continue") are cited as "<Act>, First Schedule". The
dataset excludes repealed law, so every section is marked in force.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.ingest.chunker import slugify
from app.schemas import TIER_ACT, TIER_CONSTITUTION, TIER_SL, ChunkPayload

if TYPE_CHECKING:
    from app.context import AppContext

log = logging.getLogger(__name__)

# Where a citation sends the reader to check the law. It is SSO's home page, not
# the provision: the dataset has no SSO URLs or Act codes to build a deep link from.
SSO_URL = "https://sso.agc.gov.sg"
DEFAULT_MAX_CHARS = 4000

# "14. Termination of contract", "Section 14 — Termination", "14A Interpretation", "14"
_SEC_TITLE_RX = re.compile(
    r"^\s*(?:section|sec\.?|s\.?)?\s*(\d{1,4}[A-Z]{0,3})(?=[\s.:—–-]|$)[\s.:—–-]*(.*)$",
    re.IGNORECASE)
# body opening with the number: "14.—(1) An employer …" or "14. An employer …"
_SEC_TEXT_RX = re.compile(r"^\s*(\d{1,4}[A-Z]{0,3})\.\s*[—–-]?\s*")
_SUBSECTION_RX = re.compile(r"\s(?=\(\d{1,3}[A-Z]{0,2}\)\s)")
_SENT_RX = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z“\"‘(\[])")
_SCHEDULE_RX = re.compile(r"^(?:THE\s+)?([A-Z]+)?\s*SCHEDULE\b(?:\s*[—–-]\s*continue\w*)?", re.IGNORECASE)
_PLAIN_SCHEDULE_RX = re.compile(
    r"(?:THE\s+)?(?:[A-Z]+\s+)?SCHEDULE(?:\s*[—–-]\s*continue\w*)?\.?", re.IGNORECASE)
_YEAR_RX = re.compile(r"(?:18|19|20)\d\d")
_VERSION_RX = re.compile(r"version in force from\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)
FRONT_MATTER_TITLE = "unsectioned"


_NOT_TITLE_RX = re.compile(
    r"^(?:\(No\.|\(CHAPTER|CHAPTER\s|\(Original Enactment|\(ACT\s|REVISED EDITION|"
    r"THE REVISED EDITION|UNDER THE AUTHORITY|THE LAW REVISION|Prepared and Published|"
    r"No\. S\s|First published|THE STATUTES OF)", re.IGNORECASE)


def _title_case(s: str) -> str:
    small = {"and", "of", "the", "for", "in", "on", "to", "by", "or", "a", "an", "from", "with", "under"}
    words = s.lower().split()
    return " ".join(w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def front_matter(row: dict, truncated_name: str) -> tuple[str, date | None]:
    """(full name, consolidation date) from the cover-page row.

    The name sits just above "ARRANGEMENT OF …": in proper case on revised
    editions ("Agency for Science, / Technology and Research / Act 1990"),
    otherwise in capitals ("GAMBLING REGULATORY AUTHORITY / OF SINGAPORE ACT 2022").
    The result must start like the dataset's truncated name, or it is not used."""
    text = str(row.get("text") or "")
    version = None
    if m := _VERSION_RX.search(text):
        try:
            version = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            version = None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    stem = " ".join(truncated_name.split()).casefold()
    arr = next((i for i, ln in enumerate(lines) if ln.upper().startswith("ARRANGEMENT OF")), None)
    if arr:
        def collect(upper: bool) -> str:
            got, j = [], arr - 1
            while j >= 0 and len(got) < 5:
                ln = lines[j]
                if _VERSION_RX.search(ln) or _NOT_TITLE_RX.match(ln):
                    if got:
                        break
                    j -= 1
                    continue
                if (ln == ln.upper()) != upper:
                    break
                got.insert(0, ln)
                j -= 1
            return " ".join(got)

        for upper in (False, True):
            cand = collect(upper)
            if upper:
                cand = _title_case(cand)
            if cand and cand.casefold().startswith(stem[:30]) and len(cand) >= len(stem):
                return cand, version
    return " ".join(truncated_name.split()), version


def cover_says_subsidiary(row: dict) -> bool:
    text = str(row.get("text") or "")[:1500]
    return bool(re.search(r"ARRANGEMENT OF (?:REGULATIONS|RULES|PARAGRAPHS)", text)
                or re.match(r"\s*First published in the Government Gazette", text))


_FOOTER_ED_RX = re.compile(r"^\d{4}\s+Ed\.$")
_PAGE_NO_RX = re.compile(r"^\d{1,4}$")
_SL_NAME_RX = re.compile(r"\b(Regulations?|Rules|Order|Notification|By-laws)\b")


def strip_page_furniture(text: str, doc_name: str) -> str:
    """Remove the PDF running header/footer that the dataset left inside the
    text — "<Act name> / 2020 Ed. / <page> / Informal Consolidation – version in
    force from d/m/yyyy" — wherever it falls, even mid-sentence."""
    lines = text.splitlines()
    name = " ".join(doc_name.split()).casefold()
    drop: set[int] = set()
    for i, ln in enumerate(lines):
        if not _VERSION_RX.search(ln):
            continue
        drop.add(i)
        for j in range(max(0, i - 4), min(len(lines), i + 2)):
            t = lines[j].strip()
            if (_FOOTER_ED_RX.match(t) or _PAGE_NO_RX.match(t)
                    or (t and len(t) > 3 and t.casefold() in name)):
                drop.add(j)
    return "\n".join(ln for k, ln in enumerate(lines) if k not in drop)


def document_type(rows: list[dict]) -> str:
    """The dataset labels some Regulations and Notifications as Acts; the
    cover page and the name are more reliable than the label."""
    first = rows[0]
    if str(first.get("section_title") or "").strip().casefold() == FRONT_MATTER_TITLE \
            and cover_says_subsidiary(first):
        return "subsidiary_legislation"
    t = normalise_doc_type(first.get("doc_type"))
    if t == "act" and _SL_NAME_RX.search(str(first.get("doc_name") or "")):
        return "subsidiary_legislation"
    return t


def _schedule_label(title: str) -> str | None:
    """"First Schedule" for a Schedule's heading; None for a section that merely
    mentions one, such as "First Schedule amended"."""
    title = title.strip()
    m = _SCHEDULE_RX.match(title)
    if m and (title.isupper() or _PLAIN_SCHEDULE_RX.fullmatch(title)):
        word = (m.group(1) or "").strip()
        return f"{word.title()} Schedule" if word and word.upper() != "THE" else "Schedule"
    return None


def _strip_heading(text: str, heading: str) -> str:
    """The text repeats the heading on its first line ("Short title\n1. This Act…")."""
    first, _, rest = text.partition("\n")
    if heading and rest and first.strip().casefold() == heading.strip().casefold():
        return rest
    return text


def iter_rows(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def normalise_doc_type(raw: str | None) -> str:
    """Map whatever labels the dataset uses onto ours."""
    t = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if t in {"act", "acts", "statute"} or t.startswith("act"):
        return "act"
    if t in {"sl", "subsidiary", "subsidiary_legislation"} or t.startswith("sub"):
        return "subsidiary_legislation"
    return "act"


def section_number_and_heading(row: dict) -> tuple[str | None, str]:
    title = " ".join(str(row.get("section_title") or "").split())
    m = _SEC_TITLE_RX.match(title)
    if m and not (_YEAR_RX.fullmatch(m.group(1)) and m.group(2)):  # "2000 Revised Edition"
        return m.group(1).upper(), m.group(2).strip(" .—–-")
    if _schedule_label(title):  # a Schedule's paragraph 1 is not section 1
        return None, title
    if m := _SEC_TEXT_RX.match(str(row.get("text") or "")):
        return m.group(1).upper(), title
    return None, title


def _hard_wrap(sentence: str, max_chars: int) -> list[str]:
    """A 'sentence' longer than max_chars (tables, lists without full stops) is
    cut at word boundaries."""
    out, cur = [], ""
    for w in sentence.split():
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return out + ([cur] if cur else [])


def _window_split(text: str, max_chars: int) -> list[str]:
    sentences = [piece for s in _SENT_RX.split(" ".join(text.split()))
                 for piece in (_hard_wrap(s, max_chars) if len(s) > max_chars else [s])]
    out, cur = [], ""
    for s in sentences:
        if cur and len(cur) + 1 + len(s) > max_chars:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _split_section(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces, cur = [], ""
    for part in _SUBSECTION_RX.split(text):
        if len(part) > max_chars:  # one subsection alone is too long
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.extend(_window_split(part, max_chars))
        elif cur and len(cur) + 1 + len(part) > max_chars:
            pieces.append(cur)
            cur = part
        else:
            cur = f"{cur} {part}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def _tier(doc_name: str, doc_type: str) -> int:
    if "constitution of the republic of singapore" in doc_name.lower():
        return TIER_CONSTITUTION
    return TIER_SL if doc_type == "subsidiary_legislation" else TIER_ACT


def chunks_for_document(
    doc_name: str, rows: list[dict], *, max_chars: int = DEFAULT_MAX_CHARS,
    as_at: date | None = None, doc_id: str | None = None,
) -> list[ChunkPayload]:
    as_at = as_at or date.today()
    doc_type = document_type(rows)
    version: date | None = None
    if str(rows[0].get("section_title") or "").strip().casefold() == FRONT_MATTER_TITLE:
        doc_name, version = front_matter(rows[0], doc_name)
        rows = rows[1:]
    doc_name = " ".join(doc_name.split())
    doc_id = doc_id or slugify(doc_name)
    tier = _tier(doc_name, doc_type)
    parent = rows[0].get("parent_act") if rows else None
    used_ids: set[str] = set()
    chunks: list[ChunkPayload] = []
    for idx, row in enumerate(rows, start=1):
        num, heading = section_number_and_heading(row)
        raw = strip_page_furniture(str(row.get("text") or ""), doc_name)
        text = " ".join(_strip_heading(raw, heading).split())
        if not text:
            continue
        schedule = None if num else _schedule_label(heading)
        if num:
            label, base_id = f"s {num}", f"{doc_id}:s{num}"
        elif schedule:
            label = schedule
            base_id = f"{doc_id}:sch-{slugify(schedule.replace(' Schedule', '')) or 'only'}"
        else:
            label, base_id = heading or f"part {idx}", f"{doc_id}:k{idx}"
        if base_id in used_ids:  # repeated numbers (schedules, duplicated rows)
            base_id = f"{base_id}~{idx}"
        used_ids.add(base_id)

        part, division = ("", "") if schedule else (row.get("part") or "", row.get("division") or "")
        where = "".join([f", within {part}" if part else "",
                         f", {division}" if division else ""])
        what = (f"section {num}" if num else f"the {schedule}" if schedule else "a provision")
        context = (
            f"This is {what} of the {doc_name} (Singapore){where}."
            + (f' The section is titled "{heading}".' if heading and num else "")
            + (f" It is subsidiary legislation made under the {parent}."
               if doc_type == "subsidiary_legislation" and parent else "")
            + (f" Text of the consolidated version in force from {version.isoformat()},"
               if version else " Text")
            + " taken from a published copy of Singapore Statutes Online; check SSO for the latest version."
        )
        hierarchy = [p for p in (doc_name, part, division) if p]
        hierarchy.append(f"Section {num}" + (f" — {heading}" if heading else "")
                         if num else (schedule or heading or f"Part {idx}"))
        pieces = _split_section(text, max_chars)
        for k, piece in enumerate(pieces, start=1):
            multi = len(pieces) > 1
            chunks.append(ChunkPayload(
                chunk_id=f"{base_id}.{k}" if multi else base_id,
                doc_id=doc_id,
                citation=f"{doc_name}, {label}" + (f" (part {k})" if multi else ""),
                text=piece,
                context=context,
                title=doc_name,
                doc_type=doc_type,  # type: ignore[arg-type]
                authority_tier=tier,
                status="in_force",
                hierarchy_path=hierarchy,
                source_url=SSO_URL,
                sso_version_date=version,
            ))
    return chunks


def iter_documents(path: Path, doc_types: list[str] | None = None) -> Iterator[tuple[str, list[dict]]]:
    """Group section rows into documents, keeping the dataset's order. A new
    document starts at every cover-page row as well as on a name change (an
    Act and its Regulations can share the same truncated name)."""
    wanted = {normalise_doc_type(t) for t in doc_types} if doc_types else None

    def emit(name, rows):
        return wanted is None or document_type(rows) in wanted

    current, rows = None, []
    for row in iter_rows(path):
        name = " ".join(str(row.get("doc_name") or "").split())
        if not name:
            continue
        is_cover = str(row.get("section_title") or "").strip().casefold() == FRONT_MATTER_TITLE
        if rows and (name != current or is_cover):
            if emit(current, rows):
                yield current, rows
            rows = []
        current = name
        rows.append(row)
    if rows and emit(current, rows):
        yield current, rows


def _document_ids(path: Path) -> list[str]:
    """A unique doc_id for each document, in iter_documents order. The dataset
    cuts long names at 50 characters, so different documents can share a name.
    Acts choose first, so an Act's id stays the slug of its name and lookup by
    name finds it. Ids are assigned over the whole file, so they don't depend
    on which document types are indexed."""
    docs = []
    for name, rows in iter_documents(path):
        if str(rows[0].get("section_title") or "").strip().casefold() == FRONT_MATTER_TITLE:
            name = front_matter(rows[0], name)[0]
        docs.append((slugify(name), document_type(rows)))
    taken: Counter[str] = Counter()
    ids = [""] * len(docs)
    for i in sorted(range(len(docs)), key=lambda i: docs[i][1] != "act"):
        slug = docs[i][0]
        taken[slug] += 1
        ids[i] = slug if taken[slug] == 1 else f"{slug}-{taken[slug]}"
    return ids


def iter_document_chunks(path: Path, *, doc_types: list[str] | None = None,
                         max_chars: int = DEFAULT_MAX_CHARS,
                         limit: int | None = None) -> Iterator[list[ChunkPayload]]:
    """Each wanted document's chunks. The seed step and the corpus report both
    read through here, so their chunk ids match."""
    wanted = {normalise_doc_type(t) for t in doc_types} if doc_types else None
    done = 0
    for doc_id, (name, rows) in zip(_document_ids(path), iter_documents(path), strict=True):
        if wanted is not None and document_type(rows) not in wanted:
            continue
        if limit is not None and done >= limit:
            return
        done += 1
        yield chunks_for_document(name, rows, max_chars=max_chars, doc_id=doc_id)


def all_chunks(path: Path, *, doc_types: list[str] | None = None,
               max_chars: int = DEFAULT_MAX_CHARS, limit: int | None = None) -> list[ChunkPayload]:
    return [c for chunks in iter_document_chunks(path, doc_types=doc_types, max_chars=max_chars,
                                                 limit=limit) for c in chunks]


async def ingest_sso_statutes(
    ctx: AppContext, path: Path, *, doc_types: list[str] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS, limit: int | None = None,
) -> dict[str, int]:
    from app.ingest.pipeline import upsert_chunks  # local: avoid import cycle
    from app.vectorstore import SG_LAW

    counts = {"documents": 0, "chunks": 0}
    fetched_at = datetime.now(UTC).isoformat()
    for chunks in iter_document_chunks(path, doc_types=doc_types, max_chars=max_chars, limit=limit):
        if not chunks:
            continue
        n = await upsert_chunks(ctx, SG_LAW, chunks)
        c = chunks[0]
        await ctx.db.upsert_corpus_doc(
            doc_id=c.doc_id, title=c.title, citation=c.title, doc_type=c.doc_type,
            status="in_force", authority_tier=c.authority_tier, source_url=SSO_URL,
            sso_version_date=c.sso_version_date.isoformat() if c.sso_version_date else None,
            fetched_at=fetched_at, chunk_count=n)
        counts["documents"] += 1
        counts["chunks"] += n
        if counts["documents"] % 25 == 0:
            log.info("SSO statutes: %d documents, %d chunks so far",
                     counts["documents"], counts["chunks"])
    return counts

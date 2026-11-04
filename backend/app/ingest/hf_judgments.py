"""Backup corpus: Singapore judgments from the MLEB dataset on Hugging Face.

Dataset: isaacus/singaporean-judicial-keywords (CC BY 4.0) — 500 Singapore
court judgments as plain text. Cite: Butler, Butler & Malec (2025), "The
Massive Legal Embedding Benchmark (MLEB)", arXiv:2510.19365.

corpus.jsonl rows look like {"_id": str, "title": "", "text": str}. The dataset
removed the catchwords and everything above them (case name, neutral citation,
court, decision date), so a row carries no reliable metadata of its own:

- the neutral citation and court are recovered from the dataset id, which
  encodes them (text_2002_SGCA_19 → [2002] SGCA 19), so Court of Appeal
  decisions get the binding-authority tier; other ids fall back to "MLEB-<id>";
- the case name and exact decision date are not recoverable, so judgments are
  titled "Singapore judgment [yyyy] COURT n" and left undated;
- no citation-graph edges are written for these documents, because an undated
  citing judgment could otherwise flip another judgment's treatment wrongly.

Paragraphs are segmented on the judiciary convention (a number at the start of
a line, increasing by one), exactly like judgment_parser. Text without enough
numbered paragraphs falls back to sentence-window chunks.

Used by seed_from_archive for manifest entries of kind "judgments_jsonl".
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.ingest.chunker import chunk_judgment, judgment_tier, slugify
from app.ingest.citations import NEUTRAL_RX, extract_neutral_citations
from app.ingest.judgment_parser import COURT_NAMES, Judgment, JudgmentPara
from app.schemas import COURT_LEVELS, ChunkPayload

if TYPE_CHECKING:  # avoid importing the heavy runtime context at module import
    from app.context import AppContext

log = logging.getLogger(__name__)

HF_DATASET_URL = "https://huggingface.co/datasets/isaacus/singaporean-judicial-keywords"
UNKNOWN_COURT = "Singapore court (not stated in source)"
MIN_NUMBERED = 5          # fewer numbered paragraphs than this → window fallback
DEFAULT_MAX_CHARS = 2000  # see note in the module guide: the reranker reads ~1,500 chars

_PARA_RX = re.compile(r"^(\d{1,4})\s+(\S.*)$", re.DOTALL)
# a paragraph number glued into running text: "...end of para. 12 The next..."
_INLINE_PARA_RX = re.compile(r"(?<=[.:;\"”’)\]])\s+(?=\d{1,4}\s+[A-Z“\"‘(])")
_SENT_RX = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z“\"‘(\[])")


def iter_rows(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def split_paragraphs(text: str) -> tuple[str, list[JudgmentPara]]:
    """Return (preamble, numbered paragraphs). Unnumbered lines (headings,
    quotations, list items) are appended to the paragraph they follow."""
    if text.count("\n") < 20:  # mostly one long line: recover paragraph breaks
        text = _INLINE_PARA_RX.sub("\n", text)
    preamble: list[str] = []
    paras: list[JudgmentPara] = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        m = _PARA_RX.match(line)
        if m:
            num = int(m.group(1))
            expected = paras[-1].number + 1 if paras else 1
            plausible = (expected <= num <= expected + 5) if paras else num <= 3
            if plausible:
                paras.append(JudgmentPara(number=num, text=m.group(2).strip()))
                continue
        if paras:
            paras[-1].text = f"{paras[-1].text} {line}"
        else:
            preamble.append(line)
    return " ".join(preamble), paras


_MLEB_ID_RX = re.compile(r"^text_(\d{4})_(SG[A-Z]{2,6}(?:\([A-Z]\))?)_(\d{1,4})$")


def _identity(row: dict) -> tuple[str, str, str]:
    """(neutral_citation_or_label, court_code, case_name).

    MLEB ids encode the neutral citation: text_2002_SGCA_19 → [2002] SGCA 19."""
    rid = str(row.get("_id", "")).strip()
    if m := _MLEB_ID_RX.match(rid):
        return f"[{m.group(1)}] {m.group(2)} {m.group(3)}", m.group(2), "Singapore judgment"
    if m := NEUTRAL_RX.search(rid):
        return f"[{m.group(1)}] {m.group(2)} {m.group(3)}", m.group(2), "Singapore judgment"
    return f"MLEB-{rid}", "", "Singapore judgment"


def build_judgment(row: dict) -> Judgment:
    citation, court_code, case_name = _identity(row)
    preamble, paras = split_paragraphs(row.get("text", ""))
    if paras and preamble:
        paras[0].text = f"{preamble} {paras[0].text}"
    j = Judgment(
        case_name=case_name,
        neutral_citation=citation,
        court_code=court_code,
        court=COURT_NAMES.get(court_code, UNKNOWN_COURT),
        court_level=COURT_LEVELS.get(court_code, 1),
        paragraphs=paras,
        source_url=HF_DATASET_URL,
    )
    j.cites = [c for c in extract_neutral_citations(row.get("text", "")) if c != citation]
    return j


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


def _split_oversized(chunks: list[ChunkPayload], max_chars: int) -> list[ChunkPayload]:
    """When numbering breaks (quoted clauses numbered 1, 2…, a skipped number),
    the rest of a judgment piles into one 'paragraph'. Cut any chunk over twice
    the limit into sentence windows; ids stay deterministic (<id>.1, <id>.2…)."""
    out: list[ChunkPayload] = []
    for c in chunks:
        if len(c.text) <= 2 * max_chars:
            out.append(c)
            continue
        for k, w in enumerate(_window_split(c.text, max_chars), start=1):
            out.append(c.model_copy(update={
                "chunk_id": f"{c.chunk_id}.{k}",
                "citation": f"{c.citation} (part {k})",
                "text": w,
            }))
    return out


def chunks_for_row(
    row: dict, max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[Judgment, list[ChunkPayload]]:
    j = build_judgment(row)
    if len(j.paragraphs) >= MIN_NUMBERED:
        return j, _split_oversized(chunk_judgment(j, max_chars=max_chars), max_chars)

    # fallback: no usable paragraph numbering → sentence windows
    doc_id = slugify(f"{j.neutral_citation} {j.case_name}")
    windows = _window_split(row.get("text", ""), max_chars)
    title = f"{j.case_name} {j.neutral_citation}"
    return j, [
        ChunkPayload(
            chunk_id=f"{doc_id}:part{i}",
            doc_id=doc_id,
            citation=f"{j.neutral_citation} (part {i})" if len(windows) > 1 else j.neutral_citation,
            text=w,
            context=f"This is part {i} of {len(windows)} of the judgment {title} ({j.court}).",
            title=title,
            doc_type="judgment",
            authority_tier=judgment_tier(j.court_code),
            status="in_force",
            court=j.court,
            court_level=j.court_level,
            hierarchy_path=[title, j.court, f"Part {i}"],
            source_url=HF_DATASET_URL,
            cites=j.cites,
        )
        for i, w in enumerate(windows, start=1)
    ]


async def ingest_hf_judgments(
    ctx: AppContext, path: Path, *, max_chars: int = DEFAULT_MAX_CHARS,
    limit: int | None = None,
) -> dict[str, int]:
    """Chunk, embed and index every row of corpus.jsonl into sg_law."""
    from app.ingest.pipeline import upsert_chunks  # local: pipeline imports this module
    from app.vectorstore import SG_LAW

    counts = {"documents": 0, "chunks": 0, "fallback_docs": 0}
    fetched_at = datetime.now(UTC).isoformat()
    for i, row in enumerate(iter_rows(path)):
        if limit is not None and i >= limit:
            break
        j, chunks = chunks_for_row(row, max_chars=max_chars)
        if not chunks:
            continue
        n = await upsert_chunks(ctx, SG_LAW, chunks)
        first = chunks[0]
        if len(j.paragraphs) < MIN_NUMBERED:
            counts["fallback_docs"] += 1
        if j.court_code:  # the dataset id was a real neutral citation
            await ctx.db.upsert_judgment(
                j.neutral_citation, j.case_name, j.court_code, j.court_level,
                None, first.doc_id)
        await ctx.db.upsert_corpus_doc(
            doc_id=first.doc_id, title=first.title, citation=first.title,
            doc_type="judgment", status="in_force", authority_tier=first.authority_tier,
            source_url=HF_DATASET_URL, sso_version_date=None,
            fetched_at=fetched_at, chunk_count=n)
        counts["documents"] += 1
        counts["chunks"] += n
        if counts["documents"] % 25 == 0:
            log.info("MLEB judgments: %d documents, %d chunks so far",
                     counts["documents"], counts["chunks"])
    return counts

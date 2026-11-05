"""Judgment corpus: page-sized passages from the Hugging Face dataset
badlaldh/singapore-judgments (default "judgments" config).

The dataset is 10,000 passages of about 300 words, cut from 214 Supreme Court
judgments catalogued under "Tort — Negligence" (2001-2026). It is a subset, not
the full eLitigation archive that app.elitigation indexes.

Input: data/corpus/hf_judgments/passages.jsonl, converted from the dataset's
Parquet by scripts/prepare_hf_judgments.py.

One chunk per passage, so the dataset's boundaries are kept. A passage can start
or end inside a paragraph and a long paragraph can span several passages, so
para_start..para_end is a range, not a unique key: chunk ids use the part number
instead. Paragraph numbers are not in the passage text and citation edges carry
no paragraph, because only the passage's range is known.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from app.ingest.chunker import _judgment_context, judgment_tier, slugify
from app.ingest.citations import extract_neutral_citations
from app.ingest.judgment_parser import Judgment, JudgmentPara
from app.schemas import COURT_LEVELS, ChunkPayload

if TYPE_CHECKING:
    from app.context import AppContext

log = logging.getLogger(__name__)


def iter_judgments(path: Path) -> Iterator[list[dict]]:
    """Each judgment's passages in part order. Stops on a judgment with missing
    parts, rather than index a silently partial one."""
    by_citation: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                by_citation.setdefault(row["citation"], []).append(row)
    for citation, rows in by_citation.items():
        rows.sort(key=lambda r: r["part"])
        expected = list(range(1, rows[0]["parts_total"] + 1))
        if [r["part"] for r in rows] != expected:
            raise ValueError(f"{citation}: expected parts 1..{expected[-1]}, "
                             f"found {len(rows)} passages")
        yield rows


def judgment_from_rows(rows: list[dict]) -> Judgment:
    first = rows[0]
    citation = first["citation"]
    return Judgment(
        case_name=first["case_name"],
        neutral_citation=citation,
        court_code=first["court_code"],
        court=first["court"],
        court_level=COURT_LEVELS.get(first["court_code"], 0),
        coram=list(first.get("coram") or []),
        decision_date=date.fromisoformat(first["decision_date"]) if first.get("decision_date") else None,
        catchwords=list(first.get("catchwords") or []),
        paragraphs=[JudgmentPara(r["para_start"], r["text"]) for r in rows],
        cites=[c for c in extract_neutral_citations(" ".join(r["text"] for r in rows))
               if c != citation],
        source_url=first["source_url"],
        numbered=False,  # j.paragraphs are passages: `number` is not a citable pinpoint
    )


def chunks_for_judgment(j: Judgment, rows: list[dict]) -> list[ChunkPayload]:
    doc_id = slugify(f"{j.neutral_citation} {j.case_name}")
    numbered = replace(j, numbered=True)  # the passage's own range is a real pinpoint
    chunks = []
    for r in rows:
        lo, hi = r["para_start"], r["para_end"]
        rng = f"[{lo}]" if lo == hi else f"[{lo}]–[{hi}]"
        chunks.append(ChunkPayload(
            chunk_id=f"{doc_id}:part{r['part']}",
            doc_id=doc_id,
            citation=j.neutral_citation if len(rows) == 1 else f"{j.neutral_citation} at {rng}",
            text=r["text"],
            context=_judgment_context(numbered, lo, hi),
            title=f"{j.case_name} {j.neutral_citation}",
            doc_type="judgment",
            authority_tier=judgment_tier(j.court_code),
            status="in_force",
            hierarchy_path=[f"{j.case_name} {j.neutral_citation}", j.court,
                            f"Paragraphs {rng} (passage {r['part']} of {r['parts_total']})"],
            court=j.court,
            court_level=j.court_level,
            decision_date=j.decision_date,
            cites=j.cites,
            source_url=j.source_url,
        ))
    return chunks


def all_chunks(path: Path) -> list[ChunkPayload]:
    return [c for rows in iter_judgments(path)
            for c in chunks_for_judgment(judgment_from_rows(rows), rows)]


async def ingest_hf_judgments(ctx: AppContext, path: Path) -> dict[str, int]:
    from app.ingest.pipeline import ingest_judgment  # local: avoid import cycle

    counts = {"documents": 0, "chunks": 0}
    for rows in iter_judgments(path):
        j = judgment_from_rows(rows)
        _, n = await ingest_judgment(ctx, j, chunks=chunks_for_judgment(j, rows))
        counts["documents"] += 1
        counts["chunks"] += n
        if counts["documents"] % 10 == 0:
            log.info("HF judgments: %d documents, %d chunks so far",
                     counts["documents"], counts["chunks"])
    return counts

"""Judgments: the group's Hugging Face dataset of eLitigation passages.

Dataset: badlaldh/singapore-judgments, `judgments` subset. 10,000 passages of
about 300 words (roughly one PDF page each) cut from 214 Singapore Supreme
Court judgments catalogued under Tort — Negligence, decided 2001-2026. Fields:
doc_id, part, parts_total, text, word_count, para_start, para_end, citation,
case_name, court_code, court, year, decision_date, coram, catchwords,
source_url. Paragraph numbers are not in `text`; para_start/para_end say which
paragraphs a passage covers. National ID and passport numbers are masked.

Each passage is used as one chunk, so the index and the chunk export that
Subgroup C labels from share the same ids:

    chunk_id = "<slug of citation + case name>:part<part>"

The dataset's other subsets (work/family legislation) are skipped: legislation
comes from the SSO copy (sso_statutes.py). Rows are recognised as judgment
passages by their fields, so the whole repo can be downloaded as-is.

The judgments are © Government of Singapore; keep the download private.

    uv run --with huggingface_hub hf download badlaldh/singapore-judgments \\
        --repo-type dataset --local-dir ../data/corpus/elitigation_hf
    uv run --with pyarrow python -m app.ingest.hf_elitigation status
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.ingest.chunker import judgment_tier, slugify
from app.ingest.citations import edges_from_paragraphs, extract_neutral_citations
from app.schemas import COURT_LEVELS, ChunkPayload

if TYPE_CHECKING:
    from app.context import AppContext

log = logging.getLogger(__name__)

HF_JUDGMENTS_URL = "https://huggingface.co/datasets/badlaldh/singapore-judgments"
PASSAGE_FIELDS = {"doc_id", "part", "text", "citation", "case_name", "court_code"}


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):  # a list stored as JSON text (e.g. in CSV)
            try:
                return list(json.loads(s))
            except json.JSONDecodeError:
                pass
        return [s] if s else []
    return list(v)


def _int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def is_passage(row: dict) -> bool:
    return PASSAGE_FIELDS <= row.keys()


def _rows_from_file(f: Path) -> Iterator[dict]:
    if f.suffix == ".jsonl":
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
    elif f.suffix == ".csv":
        with f.open(encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh)
    elif f.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise SystemExit("reading Parquet needs pyarrow: run with "
                             "`uv run --with pyarrow …`") from exc
        pf = pq.ParquetFile(f)
        if not PASSAGE_FIELDS <= set(pf.schema_arrow.names):
            return  # another subset (e.g. work/family legislation)
        for batch in pf.iter_batches(batch_size=500):
            yield from batch.to_pylist()


def iter_passages(folder: Path) -> Iterator[dict]:
    """Judgment-passage rows from every file under the download, in path order,
    with exact duplicates (same doc_id and part) dropped."""
    files = sorted(p for p in folder.rglob("*")
                   if p.suffix in {".parquet", ".jsonl", ".csv"} and ".cache" not in p.parts)
    if not files:
        raise FileNotFoundError(f"no .parquet, .jsonl or .csv files under {folder}")
    seen: set[tuple[str, int]] = set()
    for f in files:
        for row in _rows_from_file(f):
            if not is_passage(row):
                continue
            key = (str(row["doc_id"]), _int(row.get("part")) or 0)
            if key in seen:
                continue
            seen.add(key)
            yield row


def chunk_for_passage(row: dict) -> ChunkPayload:
    citation = " ".join(str(row.get("citation") or "").split())
    case_name = " ".join(str(row.get("case_name") or "").split())
    court_code = str(row.get("court_code") or "")
    court = str(row.get("court") or "")
    decided = _date(row.get("decision_date"))
    part, total = _int(row.get("part")) or 1, _int(row.get("parts_total"))
    lo, hi = _int(row.get("para_start")), _int(row.get("para_end"))
    text = " ".join(str(row.get("text") or "").split())

    doc_id = slugify(f"{citation} {case_name}") or slugify(str(row["doc_id"]))
    if lo is not None:
        rng = f"[{lo}]" if hi in (None, lo) else f"[{lo}]–[{hi}]"
        cite, where = f"{citation} at {rng}", f"paragraph{'s' if hi not in (None, lo) else ''} {rng}"
    else:
        rng = None
        cite, where = f"{citation} (part {part})", f"part {part}" + (f" of {total}" if total else "")
    catchwords = [str(c) for c in _as_list(row.get("catchwords"))]
    context = (
        f"This is {where} of the judgment in {case_name} {citation} ({court}"
        + (f", decided {decided.strftime('%-d %B %Y')}" if decided else "") + ")."
        + (" Catchwords: " + "; ".join(catchwords) + "." if catchwords else "")
    )
    return ChunkPayload(
        chunk_id=f"{doc_id}:part{part}",
        doc_id=doc_id,
        citation=cite,
        text=text,
        context=context,
        title=f"{case_name} {citation}".strip(),
        doc_type="judgment",
        authority_tier=judgment_tier(court_code),
        status="in_force",
        court=court or None,
        court_level=COURT_LEVELS.get(court_code, 1),
        decision_date=decided,
        hierarchy_path=[f"{case_name} {citation}".strip(), court,
                        f"Paragraphs {rng}" if rng else f"Part {part}"],
        cites=[c for c in extract_neutral_citations(text) if c != citation],
        source_url=str(row.get("source_url") or HF_JUDGMENTS_URL),
    )


def all_chunks(folder: Path, limit: int | None = None) -> list[ChunkPayload]:
    out = []
    for i, row in enumerate(iter_passages(folder)):
        if limit is not None and i >= limit:
            break
        if str(row.get("text") or "").strip():
            out.append(chunk_for_passage(row))
    return out


async def ingest_passages(ctx: AppContext, folder: Path, limit: int | None = None) -> dict[str, int]:
    """Embed and index every passage, register each judgment (so a question
    naming its citation finds it directly), and add its citation edges."""
    from app.ingest.pipeline import upsert_chunks
    from app.vectorstore import SG_LAW

    docs: dict[str, list[tuple[dict, ChunkPayload]]] = {}
    for i, row in enumerate(iter_passages(folder)):
        if limit is not None and i >= limit:
            break
        if str(row.get("text") or "").strip():
            c = chunk_for_passage(row)
            docs.setdefault(c.doc_id, []).append((row, c))
    fetched_at = datetime.now(UTC).isoformat()
    counts = {"documents": 0, "chunks": 0}
    for doc_id, pairs in docs.items():
        row, first = pairs[0]
        chunks = [c for _, c in pairs]
        n = await upsert_chunks(ctx, SG_LAW, chunks)
        neutral = " ".join(str(row.get("citation") or "").split())
        await ctx.db.upsert_judgment(
            neutral, " ".join(str(row.get("case_name") or "").split()),
            str(row.get("court_code") or ""), first.court_level or 1,
            first.decision_date.isoformat() if first.decision_date else None, doc_id)
        await ctx.db.add_citation_edges(edges_from_paragraphs(
            neutral, [(_int(r.get("para_start")), c.text) for r, c in pairs]))
        await ctx.db.upsert_corpus_doc(
            doc_id=doc_id, title=first.title, citation=neutral or first.title,
            doc_type="judgment", status="in_force", authority_tier=first.authority_tier,
            source_url=first.source_url, sso_version_date=None, fetched_at=fetched_at,
            chunk_count=n)
        counts["documents"] += 1
        counts["chunks"] += n
        if counts["documents"] % 25 == 0:
            log.info("eLitigation passages: %d judgments, %d chunks so far",
                     counts["documents"], counts["chunks"])
    return counts


# ------------------------------------------------------------------- CLI

def main() -> None:
    p = argparse.ArgumentParser(description="eLitigation judgment passages from Hugging Face")
    sub = p.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status", help="count passages, judgments and courts in the download")
    st.add_argument("--dir", default=None, help="download folder (default data/corpus/elitigation_hf)")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[3]
    folder = Path(args.dir) if args.dir else root / "data" / "corpus" / "elitigation_hf"
    rows = list(iter_passages(folder))
    # a judgment is its citation: the dataset's doc_id is per passage, not per judgment
    docs = {" ".join(str(r.get("citation") or "").split()): r for r in rows}
    print(json.dumps({
        "folder": str(folder),
        "passages": len(rows),
        "judgments": len(docs),
        "words": sum(len(str(r.get("text") or "").split()) for r in rows),
        "by_court": dict(Counter(r.get("court_code") for r in docs.values()).most_common()),
        "years": [min(int(r["year"]) for r in rows if r.get("year")),
                  max(int(r["year"]) for r in rows if r.get("year"))] if rows else [],
        "passages_without_paragraph_numbers": sum(_int(r.get("para_start")) is None for r in rows),
    }, indent=2))


if __name__ == "__main__":
    main()

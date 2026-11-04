"""Q1 corpus statistics + chunk export, read straight from the index.

    cd backend
    uv run --with matplotlib python ../scripts/corpus_report.py
    # or chunk the corpus directly, no index or embedding needed (seconds):
    uv run --with matplotlib python ../scripts/corpus_report.py --from-corpus ../data/corpus
    # or recompute from an existing export:
    uv run --with matplotlib python ../scripts/corpus_report.py --from-jsonl ../data/export/chunks.jsonl

Writes to data/export/:
  chunks.jsonl            every sg_law chunk (id, citation, doc type, status, context, text)
  corpus_stats.json       documents, chunks, words, types — overall and per document type
  chunk_length_hist.png   words per chunk, for the report

Stop `make dev` first: embedded Qdrant allows one process at a time.
Words and types are counted on chunk text only (context headers excluded),
lower-cased, tokens = runs of letters/digits (with an inner apostrophe).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_RX = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
FIELDS = ("chunk_id", "doc_id", "citation", "title", "doc_type", "status",
          "authority_tier", "court", "decision_date", "source_url", "context", "text")


def tokens(text: str) -> list[str]:
    return TOKEN_RX.findall(text.lower())


def source_of(row: dict) -> str:
    url = row.get("source_url") or ""
    if "huggingface.co" in url:
        return "MLEB judgments (Hugging Face)"
    if "sso.agc.gov.sg" in url:
        return "Singapore Statutes Online"
    if "judiciary.gov.sg" in url:
        return "Judiciary"
    return "other"


def compute_stats(rows: list[dict]) -> dict:
    def block(rs: list[dict]) -> dict:
        lengths, vocab, words = [], Counter(), 0
        for r in rs:
            t = tokens(r.get("text", ""))
            lengths.append(len(t))
            words += len(t)
            vocab.update(t)
        lengths.sort()
        return {
            "documents": len({r["doc_id"] for r in rs}),
            "chunks": len(rs),
            "words": words,
            "types": len(vocab),
            "words_per_chunk": {
                "mean": round(statistics.mean(lengths), 1) if lengths else 0,
                "median": statistics.median(lengths) if lengths else 0,
                "p95": lengths[int(0.95 * (len(lengths) - 1))] if lengths else 0,
                "max": lengths[-1] if lengths else 0,
            },
        }

    by_type, by_source = defaultdict(list), defaultdict(list)
    for r in rows:
        by_type[r.get("doc_type", "unknown")].append(r)
        by_source[source_of(r)].append(r)
    overall = block(rows)
    overall["meets_brief"] = {
        "chunks_at_least_10000": overall["chunks"] >= 10_000,
        "words_at_least_100000": overall["words"] >= 100_000,
    }
    return {
        "overall": overall,
        "by_doc_type": {k: block(v) for k, v in sorted(by_type.items())},
        "by_source": {k: block(v) for k, v in sorted(by_source.items())},
        "status_counts": dict(Counter(r.get("status", "?") for r in rows)),
    }


def scroll_index(qdrant_path: Path) -> list[dict]:
    from qdrant_client import QdrantClient

    client = QdrantClient(path=str(qdrant_path))
    rows, offset = [], None
    if not client.collection_exists("sg_law"):
        client.close()
        raise SystemExit(
            f"No index found at {qdrant_path} (collection sg_law missing).\n"
            "Run the seed step first, from the backend folder:\n"
            "  uv run python -m app.crawler seed --archive ../data/corpus\n"
            "and check its log says chunks > 0 and missing_files 0.")
    try:
        while True:
            recs, offset = client.scroll("sg_law", limit=1000, offset=offset,
                                         with_payload=True, with_vectors=False)
            rows.extend({k: r.payload.get(k) for k in FIELDS} for r in recs)
            if offset is None:
                return rows
    finally:
        client.close()


def chunk_corpus(archive_dir: Path) -> list[dict]:
    """Run the same parsers and chunkers the seed step uses, without embedding.
    Chunk ids are identical to the index's, so eval labels made from this
    export line up with retrieval results."""
    import sys
    from datetime import date

    sys.path.insert(0, str(ROOT / "backend"))
    from app.ingest.archive import read_archived
    from app.ingest.chunker import chunk_judgment, chunk_legislation, generic_chunks
    from app.ingest.hf_judgments import DEFAULT_MAX_CHARS, chunks_for_row, iter_rows
    from app.ingest.judgment_parser import parse_judgment
    from app.ingest.sso_parser import parse_legislation

    manifest = json.loads((archive_dir / "manifest.json").read_text())
    chunks = []
    for e in manifest["documents"]:
        path = archive_dir / e["path"]
        if not path.exists():
            print(f"missing, skipped: {e['path']}")
            continue
        kind, url = e["kind"], e.get("source_url", "")
        if kind == "judgments_jsonl":
            for i, row in enumerate(iter_rows(path)):
                if e.get("limit") is not None and i >= e["limit"]:
                    break
                chunks += chunks_for_row(row, max_chars=e.get("max_chars", DEFAULT_MAX_CHARS))[1]
        elif kind == "legislation":
            doc = parse_legislation(read_archived(path), source_url=url, doc_type=e.get("doc_type"))
            chunks += chunk_legislation(doc, as_at=date.today())
        elif kind == "judgment":
            chunks += chunk_judgment(parse_judgment(read_archived(path), source_url=url))
        elif kind == "practice_direction":
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(read_archived(path), "lxml")
            text = "\n\n".join(t.get_text(" ", strip=True)
                                for t in soup.find_all(["p", "div", "li", "h1", "h2", "h3"])
                                if t.get_text(strip=True))
            chunks += generic_chunks(text, title=e.get("title", e["path"]),
                                     doc_type="practice_direction", source_url=url)
    return [{k: c.model_dump(mode="json").get(k) for k in FIELDS} for c in chunks]


def plot(rows: list[dict], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = defaultdict(list)
    for r in rows:
        groups[r.get("doc_type", "unknown")].append(len(tokens(r.get("text", ""))))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(list(groups.values()), bins=40, stacked=True, label=list(groups.keys()))
    ax.set_xlabel("Words per chunk")
    ax.set_ylabel("Chunks")
    ax.set_title(f"Chunk length distribution ({len(rows):,} chunks)")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=200)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", type=Path, default=ROOT / "data" / "qdrant")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "export")
    ap.add_argument("--from-jsonl", type=Path, help="recompute from an existing chunks.jsonl")
    ap.add_argument("--from-corpus", type=Path,
                    help="chunk an archive folder (e.g. ../data/corpus) without the index")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if args.from_jsonl:
        rows = [json.loads(line) for line in args.from_jsonl.open() if line.strip()]
    else:
        rows = chunk_corpus(args.from_corpus) if args.from_corpus else scroll_index(args.qdrant)
        with (args.out / "chunks.jsonl").open("w") as fh:
            for r in sorted(rows, key=lambda r: r["chunk_id"]):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = compute_stats(rows)
    (args.out / "corpus_stats.json").write_text(json.dumps(stats, indent=2))
    if not args.no_plot:
        plot(rows, args.out / "chunk_length_hist.png")

    o = stats["overall"]
    print(f"documents {o['documents']:,} · chunks {o['chunks']:,} · "
          f"words {o['words']:,} · types {o['types']:,}")
    for k, v in stats["by_doc_type"].items():
        print(f"  {k:<24} docs {v['documents']:>6,}  chunks {v['chunks']:>7,}  words {v['words']:>10,}")
    print("meets brief:", o["meets_brief"])
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()

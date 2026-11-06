"""Run SingLaw over a labelled benchmark CSV (data/export/benchmark/<name>.csv).

For each question it records:
  - the top-20 retrieved chunks (doc_id + citation) and recall@k against gold_doc_ids
  - the generated answer and its sources (via the same /api/chat pipeline)

Writes data/export/benchmark/<name>.results.jsonl, which eval/judge_benchmark.py grades.

    cd backend && uv run python ../eval/run_benchmark.py haotien [--limit N]

Needs the published index in data/ (`make index`, needs HF_TOKEN) and, for real
generated answers, MINIMAX_API_KEY (without it the answer is the extractive fallback).
Stop the API server first: embedded Qdrant is single-process.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.answer import chat_stream  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.context import build_context, shutdown_context  # noqa: E402
from app.retrieval import analyze_query, retrieve  # noqa: E402
from app.vectorstore import SG_LAW  # noqa: E402

KS = (1, 5, 10, 20)


async def answer(ctx, question: str) -> tuple[str, list[dict]]:
    text, sources = "", []
    async for frame in chat_stream(ctx, question, None, None):
        for line in frame.strip().split("\n"):
            if line.startswith("data: "):
                d = json.loads(line[len("data: "):])
                if "text" in d:
                    text += d["text"]
                elif "sources" in d:
                    sources = d["sources"]
    return text, sources


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-generate", action="store_true", help="retrieval metrics only")
    args = ap.parse_args()

    bench = ROOT / "data" / "export" / "benchmark"
    rows = list(csv.DictReader(open(bench / f"{args.name}.csv", encoding="utf-8")))[: args.limit]
    # The index stores Acts under the same doc_id as the benchmark, but judgments per case;
    # a gold judgment passage is matched by its chunk citation ("[2004] SGHC 95 at [11]–[14]").
    keys = json.load(open(bench / f"{args.name}.gold_index_keys.json", encoding="utf-8"))

    def hit(gold_id: str, chunk) -> bool:
        k = keys[gold_id]
        return chunk.payload.doc_id == k["doc_id"] if "doc_id" in k else chunk.payload.citation == k["citation"]
    out_path = bench / f"{args.name}.results.jsonl"
    done = set()
    if out_path.exists():  # resumable
        done = {json.loads(l)["question_id"] for l in out_path.open(encoding="utf-8") if l.strip()}

    settings = get_settings()
    ctx = await build_context(settings)
    try:
        if await ctx.store.count(SG_LAW) == 0:
            sys.exit("sg_law collection is empty - run `make index` first (needs HF_TOKEN).")
        with out_path.open("a", encoding="utf-8") as out:
            for r in rows:
                if r["question_id"] in done:
                    continue
                t0 = time.perf_counter()
                gold = r["gold_doc_ids"].split("|")
                analysis = await analyze_query(ctx, r["question"])
                result = await retrieve(ctx, r["question"], analysis=analysis)
                top = result.chunks[:20]

                def recall(k: int) -> float:
                    return sum(any(hit(g, c) for c in top[:k]) for g in gold) / len(gold)

                rec = {
                    "question_id": r["question_id"],
                    "question_type": r["question_type"],
                    "source_type": r["source_type"],
                    "gold_doc_ids": gold,
                    "retrieved": [{"doc_id": c.payload.doc_id, "citation": c.payload.citation}
                                  for c in top],
                    **{f"recall@{k}": recall(k) for k in KS},
                    "low_confidence": result.low_confidence,
                    "refused": analysis.out_of_scope or analysis.wants_drafting,
                }
                if not args.no_generate:
                    rec["answer"], srcs = await answer(ctx, r["question"])
                    rec["sources"] = [s.get("citation", "") for s in srcs]
                rec["seconds"] = round(time.perf_counter() - t0, 1)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                print(f"{r['question_id']} recall@20={rec['recall@20']:.2f} ({rec['seconds']}s)")
    finally:
        await shutdown_context(ctx)

    res = [json.loads(l) for l in out_path.open(encoding="utf-8") if l.strip()]
    print(f"\n{len(res)} results in {out_path}")
    for k in KS:
        print(f"  recall@{k}: {sum(x[f'recall@{k}'] for x in res) / len(res):.3f}")


if __name__ == "__main__":
    asyncio.run(main())

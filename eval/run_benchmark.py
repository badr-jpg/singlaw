"""Run SingLaw on a labelled benchmark CSV and grade the answers with Claude.

    cd backend && uv run --with anthropic python ../eval/run_benchmark.py \
        --csv ../data/export/benchmark/sumo.csv

For each question it measures:
  recall@k        share of gold_doc_ids found among the top-k retrieved chunks
  hit@k           all gold documents retrieved
  answer score    Claude's grade of SingLaw's answer against the reference
                  answer and evidence: correct=1, partial=0.5, incorrect/refused=0
  unsupported     Claude flags claims that contradict or go beyond the evidence

The judge uses the Anthropic SDK when ANTHROPIC_API_KEY (or another SDK
credential) is set, otherwise the `claude` CLI in headless mode. Results are
cached per question in <out>.jsonl so an interrupted run resumes where it
stopped; delete that file to start again. Needs the published index
(`make index`) — the bundled dev archive does not contain the benchmark
documents, and the script refuses to run if most gold documents are missing.

Stop `make dev` first: embedded Qdrant is single-process.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent / "backend"))

from app.answer import chat_stream, validate_grounding  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.context import build_context, shutdown_context  # noqa: E402
from app.retrieval import analyze_query, retrieve  # noqa: E402
from app.vectorstore import SG_LAW  # noqa: E402

JUDGE_MODEL = "claude-opus-5-5"
SCORES = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0, "refused": 0.0}

JUDGE_SYSTEM = """You grade answers from a Singapore legal-information assistant against a labelled benchmark.

You receive a question, a reference answer, the gold evidence (exact quotes from the source documents with their citations) and the assistant's answer. The reference answer and evidence are ground truth; do not use outside legal knowledge.

Verdicts:
- correct: the answer gives the substance of the reference answer (the key rule, number, holding or outcome) with nothing that contradicts it. Extra detail is fine if it does not contradict the evidence.
- partial: the answer gets some of the key points but misses or muddles others, or answers only part of a multi-part question.
- incorrect: the answer's main point is wrong, contradicts the evidence, or is about a different provision or case.
- refused: the answer declines, says it could not find authority, or gives no substantive answer.

Set unsupported_claims to true if the answer asserts a specific legal fact (a number, deadline, penalty, holding) that contradicts the evidence. Keep the rationale to one or two sentences."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(SCORES)},
        "unsupported_claims": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": ["verdict", "unsupported_claims", "rationale"],
    "additionalProperties": False,
}


def judge_prompt(row: dict, answer: str) -> str:
    ev = "\n".join(f"- {c}: \"{q}\"" for c, q in zip(row["gold_citations"].split("|"),
                                                     row["evidence_quote"].split("|")))
    return (f"<question>\n{row['question']}\n</question>\n\n"
            f"<reference_answer>\n{row['answer']}\n</reference_answer>\n\n"
            f"<evidence>\n{ev}\n</evidence>\n\n"
            f"<assistant_answer>\n{answer or '(empty)'}\n</assistant_answer>\n\n"
            "Grade the assistant's answer.")


class Judge:
    def __init__(self, mode: str, model: str):
        self.model = model
        if mode == "auto":
            mode = "api" if (os.environ.get("ANTHROPIC_API_KEY")
                             or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else "cli"
        self.mode = mode
        if mode == "api":
            import anthropic
            self.client = anthropic.Anthropic()
        elif not shutil.which("claude"):
            raise SystemExit("No ANTHROPIC_API_KEY and no `claude` CLI on PATH — cannot judge.")

    def grade(self, row: dict, answer: str) -> dict:
        prompt = judge_prompt(row, answer)
        if self.mode == "api":
            r = self.client.messages.create(
                model=self.model, max_tokens=16000, system=JUDGE_SYSTEM,
                output_config={"effort": "medium",
                               "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
                messages=[{"role": "user", "content": prompt}])
            if r.stop_reason == "refusal":
                return {"verdict": "error", "unsupported_claims": False,
                        "rationale": "judge refused"}
            text = next(b.text for b in r.content if b.type == "text")
            return json.loads(text)
        out = subprocess.run(
            ["claude", "-p", "--model", self.model, "--output-format", "json",
             "--system-prompt", JUDGE_SYSTEM, "--json-schema", json.dumps(JUDGE_SCHEMA),
             "--tools", "", "--no-session-persistence"],
            input=prompt, capture_output=True, text=True, timeout=600)
        if out.returncode:
            raise RuntimeError(f"claude CLI failed: {out.stderr[:300]}")
        res = json.loads(out.stdout)
        if isinstance(res.get("structured_output"), dict):
            return res["structured_output"]
        txt = res.get("result", "").strip().removeprefix("```json").removesuffix("```")
        return json.loads(txt)


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


async def index_coverage(ctx, rows: list[dict]) -> float:
    gold = sorted({g for r in rows for g in r["gold_doc_ids"].split("|")})
    found = 0
    for g in gold:
        if await ctx.store.by_doc_id(SG_LAW, g):
            found += 1
    return found / len(gold) if gold else 0.0


def summarise(results: list[dict]) -> dict:
    def agg(rs: list[dict]) -> dict:
        judged = [r for r in rs if r.get("verdict") in SCORES]
        return {
            "n": len(rs),
            "recall_at_k": sum(r["recall"] for r in rs) / len(rs) if rs else None,
            "hit_at_k": sum(r["hit_all"] for r in rs) / len(rs) if rs else None,
            "answer_score": (sum(SCORES[r["verdict"]] for r in judged) / len(judged)
                             if judged else None),
            "correct_rate": (sum(r["verdict"] == "correct" for r in judged) / len(judged)
                             if judged else None),
            "unsupported_rate": (sum(r["unsupported_claims"] for r in judged) / len(judged)
                                 if judged else None),
            "ungrounded_rate": (sum(r["ungrounded"] for r in rs) / len(rs) if rs else None),
            "verdicts": {v: sum(r.get("verdict") == v for r in rs)
                         for v in list(SCORES) + ["error"]},
        }
    by = {k: defaultdict(list) for k in ("question_type", "source_type")}
    for r in results:
        for k in by:
            by[k][r[k]].append(r)
    return {"overall": agg(results),
            **{f"by_{k}": {v: agg(rs) for v, rs in sorted(d.items())} for k, d in by.items()}}


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    ap.add_argument("--judge", choices=["auto", "api", "cli", "none"], default="auto")
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--out", type=Path, help="default: eval/results_<csv stem>.json")
    ap.add_argument("--allow-missing-index", action="store_true",
                    help="run even if the index lacks most gold documents")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))[: a.limit]
    out = a.out or EVAL_DIR / f"results_{a.csv.stem}.json"
    cache_path = out.with_suffix(".jsonl")
    done = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["question_id"]] = r
    judge = None if a.judge == "none" else Judge(a.judge, a.judge_model)

    settings = get_settings()
    ctx = await build_context(settings)
    try:
        cov = await index_coverage(ctx, rows)
        print(f"index holds {cov:.0%} of the gold documents "
              f"(profile={settings.model_profile}, llm={'yes' if ctx.llm.configured else 'no'}, "
              f"judge={judge.mode + ':' + judge.model if judge else 'none'})")
        if cov < 0.5 and not a.allow_missing_index:
            raise SystemExit("The index is missing most benchmark documents — run `make index` "
                             "(needs HF_TOKEN) or pass --allow-missing-index.")

        results = []
        with open(cache_path, "a", encoding="utf-8") as cache:
            for i, row in enumerate(rows, 1):
                qid = row["question_id"]
                if qid in done and (judge is None or done[qid].get("verdict") in SCORES):
                    results.append(done[qid])
                    continue
                q = row["question"]
                analysis = await analyze_query(ctx, q)
                ret = await retrieve(ctx, q, analysis=analysis)
                top = ret.chunks[: a.k]
                got = [(c.payload.doc_id, c.payload.chunk_id) for c in top]
                gold = row["gold_doc_ids"].split("|")
                hits = [g for g in gold
                        if any(d == g or cid.startswith(g) for d, cid in got)]
                text, sources = await answer(ctx, q)
                v = validate_grounding(text, len(sources))
                r = {
                    "question_id": qid, "question_type": row["question_type"],
                    "source_type": row["source_type"], "question": q,
                    "gold_doc_ids": gold, "retrieved_doc_ids": [d for d, _ in got],
                    "recall": len(hits) / len(gold), "hit_all": len(hits) == len(gold),
                    "low_confidence": ret.low_confidence,
                    "answer": text, "cited": [s.get("citation") for s in sources],
                    "ungrounded": not v["grounded"],
                }
                if judge:
                    try:
                        r.update(await asyncio.to_thread(judge.grade, row, text))
                    except Exception as e:  # keep going; rerun retries errored rows
                        r.update({"verdict": "error", "unsupported_claims": False,
                                  "rationale": f"{type(e).__name__}: {e}"[:300]})
                results.append(r)
                cache.write(json.dumps(r) + "\n")
                cache.flush()
                print(f"  [{i:>3}/{len(rows)}] {qid} {row['question_type']:<16} "
                      f"recall={r['recall']:.2f} verdict={r.get('verdict', '-')}")

        summary = summarise(results)
        summary.update({"csv": str(a.csv), "k": a.k, "profile": settings.model_profile,
                        "judge": f"{judge.mode}:{judge.model}" if judge else None,
                        "index_coverage": cov})
        print("\n================ summary ================")
        o = summary["overall"]
        for key in ("recall_at_k", "hit_at_k", "answer_score", "correct_rate",
                    "unsupported_rate", "ungrounded_rate"):
            val = o[key]
            print(f"{key:>18}: {val:.3f}" if val is not None else f"{key:>18}: n/a")
        print(f"{'verdicts':>18}: {o['verdicts']}")
        for k in ("by_question_type", "by_source_type"):
            for name, s in summary[k].items():
                score = f"{s['answer_score']:.2f}" if s["answer_score"] is not None else "n/a"
                print(f"  {name:<18} n={s['n']:<4} recall@{a.k}={s['recall_at_k']:.2f} "
                      f"answer={score}")
        out.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
        print(f"\nwritten: {out}")
    finally:
        await shutdown_context(ctx)


if __name__ == "__main__":
    asyncio.run(main())

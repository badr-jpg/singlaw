"""Retrieval + grounding evaluation (spec Part 8).

Measures, against eval/questions.jsonl:
  recall@20            — expected citations present in the top-20 (prefix match)
  citation accuracy    — [CITE:n] markers that resolve to a real source
  hallucination rate   — answers containing propositions no retrieved chunk backs
  refusal correctness  — out-of-scope / drafting questions actually refused

Run via `make eval`. Uses the configured profile and data dir; seeds the
bundled archive automatically when the corpus is empty. Reporting tool —
prints a table and writes eval/results.json; it never asserts.

NOTE: embedded Qdrant is single-process — stop the API server first, or this
will block waiting for the storage lock.
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent / "backend"))

from app.answer import chat_stream, validate_grounding
from app.config import get_settings
from app.context import build_context, shutdown_context
from app.ingest.pipeline import seed_from_archive
from app.retrieval import analyze_query, retrieve
from app.vectorstore import SG_LAW

REFUSAL_INTENTS = {"out_of_scope", "drafting_refused"}


def load_questions() -> list[dict]:
    return [json.loads(line) for line in
            (EVAL_DIR / "questions.jsonl").read_text().splitlines() if line.strip()]


async def eval_question(ctx, q: dict) -> dict:
    analysis = await analyze_query(ctx, q["question"])
    out: dict = {"id": q["id"], "category": q["category"]}

    if q.get("expect_refusal"):
        refused = analysis.out_of_scope or analysis.wants_drafting
        if not refused and ctx.llm.configured:
            # without an LLM only the heuristics can refuse; with one, trust analysis
            pass
        out["refused"] = refused
        out["correct_refusal"] = refused
        return out

    result = await retrieve(ctx, q["question"], analysis=analysis)
    got = [c.payload.citation for c in result.chunks[:20]]
    expected = q.get("expected_citations", [])
    hits = [e for e in expected if any(g.startswith(e) or e.startswith(g) for g in got)]
    out.update({
        "recall": len(hits) / len(expected) if expected else None,
        "hit_all": len(hits) == len(expected),
        "missing": [e for e in expected if e not in hits],
        "low_confidence": result.low_confidence,
        "false_refusal": analysis.out_of_scope or analysis.wants_drafting,
    })

    # generation-side metrics (works offline via the extractive fallback)
    text, n_sources = "", 0
    async for frame in chat_stream(ctx, q["question"], None, None):
        for line in frame.strip().split("\n"):
            if line.startswith("data: "):
                d = json.loads(line[len("data: "):])
                if "text" in d:
                    text += d["text"]
                elif "sources" in d:
                    n_sources = len(d["sources"])
    v = validate_grounding(text, n_sources)
    total_cites = text.count("[CITE:")
    out["citation_accuracy"] = (
        (total_cites - len(v["invalid_cites"])) / total_cites if total_cites else None)
    out["hallucinated"] = not v["grounded"]
    return out


async def main() -> None:
    settings = get_settings()
    ctx = await build_context(settings)
    try:
        if await ctx.store.count(SG_LAW) == 0:
            print("corpus empty — seeding bundled archive …")
            await seed_from_archive(ctx, settings.archive_dir)

        questions = load_questions()
        results = []
        for q in questions:
            r = await eval_question(ctx, q)
            results.append(r)
            mark = ("REFUSED-OK" if r.get("correct_refusal")
                    else "MISSED-REFUSAL" if "correct_refusal" in r
                    else f"recall={r['recall']:.2f}" if r.get("recall") is not None
                    else "-")
            print(f"  q{q['id']:>2} [{q['category']:<16}] {mark}")

        # ---- aggregate ----
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for r in results:
            by_cat[r["category"]].append(r)

        answerable = [r for r in results if "recall" in r]
        refusals = [r for r in results if "correct_refusal" in r]
        cited = [r for r in answerable if r.get("citation_accuracy") is not None]
        summary = {
            "n": len(results),
            "recall_at_20": (sum(r["recall"] for r in answerable) / len(answerable))
            if answerable else None,
            "full_hit_rate": (sum(r["hit_all"] for r in answerable) / len(answerable))
            if answerable else None,
            "citation_accuracy": (sum(r["citation_accuracy"] for r in cited) / len(cited))
            if cited else None,
            "hallucination_rate": (sum(r["hallucinated"] for r in answerable)
                                   / len(answerable)) if answerable else None,
            "refusal_correctness": (sum(r["correct_refusal"] for r in refusals)
                                    / len(refusals)) if refusals else None,
            "false_refusal_rate": (sum(r.get("false_refusal", False) for r in answerable)
                                   / len(answerable)) if answerable else None,
            "by_category": {
                cat: {
                    "n": len(rs),
                    "recall_at_20": (sum(r["recall"] for r in rs if r.get("recall") is not None)
                                     / max(1, len([r for r in rs if r.get("recall") is not None])))
                    if any(r.get("recall") is not None for r in rs) else None,
                    "refusal_correctness": (sum(r.get("correct_refusal", False) for r in rs)
                                            / len(rs)) if cat == "out_of_scope" else None,
                }
                for cat, rs in sorted(by_cat.items())
            },
            "profile": settings.model_profile,
            "llm_configured": ctx.llm.configured,
        }

        print("\n================ summary ================")
        for key in ("recall_at_20", "full_hit_rate", "citation_accuracy",
                    "hallucination_rate", "refusal_correctness", "false_refusal_rate"):
            val = summary[key]
            print(f"{key:>22}: {val:.3f}" if val is not None else f"{key:>22}: n/a")
        for cat, s in summary["by_category"].items():
            extra = (f"refusal={s['refusal_correctness']:.2f}"
                     if s["refusal_correctness"] is not None
                     else f"recall={s['recall_at_20']:.2f}" if s["recall_at_20"] is not None
                     else "")
            print(f"  {cat:<18} n={s['n']:<3} {extra}")
        print(f"(profile={summary['profile']}, llm={'yes' if summary['llm_configured'] else 'no'})")

        (EVAL_DIR / "results.json").write_text(
            json.dumps({"summary": summary, "results": results}, indent=2))
        print(f"\nwritten: {EVAL_DIR / 'results.json'}")
    finally:
        await shutdown_context(ctx)


if __name__ == "__main__":
    asyncio.run(main())

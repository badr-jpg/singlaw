"""Score SingLaw's benchmark answers with Claude as the judge (RAGAS-style).

    export ANTHROPIC_API_KEY=...
    cd backend && uv run --with anthropic python ../eval/judge_claude.py darien

Reads eval/results/<name>_results.jsonl (from run_ragas_benchmark.py) and asks
Claude, for each question, to compare SingLaw's answer with the gold answer
and the sources SingLaw was given. Per question it records:

  faithfulness        share of the answer's claims supported by the sources
  answer_correctness  agreement with the gold answer (1 / 0.5 / 0)
  answer_relevancy    how directly the answer addresses the question
  context_precision   average precision of the sources Claude marks relevant
  context_recall      share of gold evidence quotes present in the sources
                      (computed by run_ragas_benchmark.py, no judge needed)

Writes eval/results/<name>_judged.jsonl (resumable) and <name>_judge.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "eval" / "results"

SYSTEM = """You are a strict evaluator of a retrieval-augmented legal assistant for Singapore law.
You judge only against the material given to you: the question, the reference answer written from the gold evidence, the gold evidence quotes, and the numbered sources the assistant was given. Do not use outside legal knowledge.
Return only a JSON object, no prose."""

PROMPT = """QUESTION
{question}

REFERENCE ANSWER
{reference}

GOLD EVIDENCE
{evidence}

SOURCES GIVEN TO THE ASSISTANT
{sources}

ASSISTANT ANSWER
{answer}

Score the assistant answer. Return JSON with exactly these keys:
- "claims": list of the distinct factual or legal claims in the assistant answer (short strings; ignore disclaimers and suggestions to see a lawyer)
- "unsupported_claims": the claims from "claims" that no numbered source supports
- "answer_correctness": 1 if the answer gives the substance of the reference answer with nothing contradicting it, 0.5 if partly correct or incomplete, 0 if wrong, contradictory, or a refusal / "could not find"
- "answer_relevancy": 1 if the answer directly addresses the question, 0.5 if partly or with much irrelevant material, 0 if it does not address it
- "relevant_sources": list of source numbers that contain information needed to answer the question
- "refused": true if the assistant declined or said it could not find the answer
- "reason": one sentence explaining the correctness score"""


def build_prompt(r: dict) -> str:
    srcs = "\n\n".join(f"[{s['n']}] {s.get('citation', '')}\n{s.get('text', '')}"
                       for s in r.get("sources", [])) or "(none)"
    ev = "\n".join(f"- {c}: \"{q}\"" for c, q in zip(r["gold_citations"].split("|"),
                                                     r["evidence_quote"].split("|")))
    return PROMPT.format(question=r["question"], reference=r["answer"], evidence=ev,
                         sources=srcs, answer=r.get("generated_answer") or "(empty)")


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def score(r: dict, j: dict) -> dict:
    claims = j.get("claims") or []
    unsup = j.get("unsupported_claims") or []
    rel = {int(n) for n in j.get("relevant_sources") or [] if str(n).isdigit()}
    order = [s["n"] for s in r.get("sources", [])]
    hits, precs = 0, []
    for i, n in enumerate(order, start=1):
        if n in rel:
            hits += 1
            precs.append(hits / i)
    return {
        "faithfulness": (len(claims) - len(unsup)) / len(claims) if claims else
                        (1.0 if j.get("refused") else 0.0),
        "answer_correctness": float(j.get("answer_correctness", 0)),
        "answer_relevancy": float(j.get("answer_relevancy", 0)),
        "context_precision": sum(precs) / len(precs) if precs else 0.0,
        "context_recall": r.get("context_recall"),
        "refused": bool(j.get("refused")),
    }


def summarise(judged: list[dict]) -> dict:
    keys = ["faithfulness", "answer_correctness", "answer_relevancy",
            "context_precision", "context_recall", "refused"]

    def avg(rs):
        out = {"n": len(rs)}
        for k in keys:
            v = [float(r["scores"][k]) for r in rs if r["scores"].get(k) is not None]
            out[k] = round(sum(v) / len(v), 4) if v else None
        return out

    by = defaultdict(list)
    for r in judged:
        by[f"type={r['question_type']}"].append(r)
        by[f"source={r['source_type']}"].append(r)
    return {"overall": avg(judged), **{k: avg(v) for k, v in sorted(by.items())}}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    results = [json.loads(l) for l in
               (RES / f"{a.name}_results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out_path = RES / f"{a.name}_judged.jsonl"
    done = {}
    if out_path.exists():
        for l in out_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                done[d["question_id"]] = d
    todo = [r for r in results if r["question_id"] not in done and "generated_answer" in r]
    print(f"{len(results)} results, {len(done)} already judged, {len(todo)} to judge with {a.model}")

    sem = asyncio.Semaphore(a.concurrency)
    lock = asyncio.Lock()

    async def judge(r: dict) -> None:
        async with sem:
            for attempt in range(3):
                try:
                    msg = await client.messages.create(
                        model=a.model, max_tokens=1500, system=SYSTEM,
                        messages=[{"role": "user", "content": build_prompt(r)}])
                    j = parse_json("".join(b.text for b in msg.content if b.type == "text"))
                    break
                except Exception as e:  # noqa: BLE001 — retry on API or JSON errors
                    if attempt == 2:
                        print(f"  {r['question_id']} failed: {e}")
                        return
                    await asyncio.sleep(2 ** attempt)
        rec = {k: r[k] for k in ("question_id", "question_type", "source_type")}
        rec.update(judge=j, scores=score(r, j), model=a.model)
        async with lock:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done[r["question_id"]] = rec
            s = rec["scores"]
            print(f"  {r['question_id']} correct={s['answer_correctness']:.1f} "
                  f"faith={s['faithfulness']:.2f} cp={s['context_precision']:.2f}")

    await asyncio.gather(*(judge(r) for r in todo))

    judged = [done[r["question_id"]] for r in results if r["question_id"] in done]
    summary = summarise(judged)
    (RES / f"{a.name}_judge.json").write_text(json.dumps(summary, indent=2))
    cols = ["n", "faithfulness", "answer_correctness", "answer_relevancy",
            "context_precision", "context_recall", "refused"]
    print(f"\n{'':<26}" + "".join(f"{c[:12]:>13}" for c in cols))
    for k, s in summary.items():
        print(f"{k:<26}" + "".join(
            f"{s['n']:>13d}" if c == "n" else
            (f"{s[c]:>13.3f}" if s[c] is not None else f"{'n/a':>13}") for c in cols))


if __name__ == "__main__":
    asyncio.run(main())

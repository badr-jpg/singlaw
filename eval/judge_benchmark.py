"""Grade SingLaw answers with Claude as the judge.

Reads data/export/benchmark/<name>.csv (gold) and <name>.results.jsonl (from
run_benchmark.py), asks Claude to grade each generated answer against the gold
answer and evidence, and writes <name>.judged.jsonl plus a summary.

    cd backend && uv run --with anthropic python ../eval/judge_benchmark.py haotien

Needs Anthropic credentials (ANTHROPIC_API_KEY, or a profile from `ant auth login`).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5-5"

SYSTEM = """You grade answers from a Singapore legal-information assistant against a labelled benchmark.
You get the question, a gold answer, verbatim evidence from the source documents, and the assistant's answer.
Judge only against the gold answer and evidence, not outside legal knowledge.
- correctness: "correct" if the answer states the key facts of the gold answer without contradicting it;
  "partial" if it is right but misses or blurs a key element; "incorrect" if it is wrong, contradicts the
  gold answer, or does not answer (a refusal or "I couldn't find this" counts as incorrect).
- faithful: false if the answer asserts something material that the evidence or gold answer contradicts.
- cites_right_source: true if the answer's citations include the gold source (Act and section, or case).
Keep the rationale to one or two sentences."""


class Verdict(BaseModel):
    correctness: Literal["correct", "partial", "incorrect"]
    faithful: bool
    cites_right_source: bool
    rationale: str


def judge(client: anthropic.Anthropic, gold: dict, res: dict) -> Verdict:
    prompt = (f"Question: {gold['question']}\n\nGold answer: {gold['answer']}\n\n"
              f"Gold citations: {gold['gold_citations']}\n\n"
              f"Evidence: {gold['evidence_quote']}\n\n"
              f"Assistant's answer:\n{res.get('answer', '')}\n\n"
              f"Assistant's sources: {'; '.join(res.get('sources', []))}")
    resp = client.messages.parse(
        model=MODEL, max_tokens=4000, system=SYSTEM,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
        output_format=Verdict,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"judge refused {gold['question_id']}")
    return resp.parsed_output


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    args = ap.parse_args()
    bench = ROOT / "data" / "export" / "benchmark"
    gold = {r["question_id"]: r for r in csv.DictReader(open(bench / f"{args.name}.csv", encoding="utf-8"))}
    results = [json.loads(l) for l in open(bench / f"{args.name}.results.jsonl", encoding="utf-8") if l.strip()]
    out_path = bench / f"{args.name}.judged.jsonl"
    done = {}
    if out_path.exists():
        done = {j["question_id"]: j for j in map(json.loads, out_path.open(encoding="utf-8")) if j}

    client = anthropic.Anthropic()
    with out_path.open("a", encoding="utf-8") as out:
        for res in results:
            q = res["question_id"]
            if q in done or "answer" not in res:
                continue
            v = judge(client, gold[q], res)
            done[q] = {"question_id": q, "question_type": res["question_type"],
                       "recall@20": res["recall@20"], **v.model_dump()}
            out.write(json.dumps(done[q], ensure_ascii=False) + "\n")
            out.flush()
            print(f"{q}: {v.correctness}{'' if v.faithful else ' UNFAITHFUL'}")

    score = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}
    groups = defaultdict(list)
    for j in done.values():
        groups["ALL"].append(j)
        groups[j["question_type"]].append(j)
    print(f"\n{'group':<18}{'n':>4}{'score':>8}{'correct':>9}{'faithful':>10}{'cites':>7}{'R@20':>7}")
    for g, js in sorted(groups.items()):
        n = len(js)
        print(f"{g:<18}{n:>4}{sum(score[j['correctness']] for j in js) / n:>8.3f}"
              f"{sum(j['correctness'] == 'correct' for j in js) / n:>9.3f}"
              f"{sum(j['faithful'] for j in js) / n:>10.3f}"
              f"{sum(j['cites_right_source'] for j in js) / n:>7.3f}"
              f"{sum(j['recall@20'] for j in js) / n:>7.3f}")


if __name__ == "__main__":
    main()

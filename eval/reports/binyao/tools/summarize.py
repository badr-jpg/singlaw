"""Combine the run with the judge verdicts; write <name>_summary.json and <name>_results.csv.
judge: correct 2 = correct and complete, 1 = partly correct, 0 = wrong / refused
usage: python -I -X utf8 summarize.py <repo> <name> [tag] [llm label]"""
import collections, csv, json, os, re, sys
repo, name = sys.argv[1], sys.argv[2]
tag = ("_" + sys.argv[3]) if len(sys.argv) > 3 else ""
llm = sys.argv[4] if len(sys.argv) > 4 else "glm-4-flash"
b = os.path.join(repo, "data", "export", "benchmark")
run = {o["question_id"]: o for o in map(json.loads, open(os.path.join(b, f"{name}_run{tag}.jsonl"), encoding="utf-8"))}
judge = {o["question_id"]: o for o in map(json.loads, open(os.path.join(b, f"{name}_judge{tag}.jsonl"), encoding="utf-8"))}


def frac_at(ranks, k):
    return sum(1 for r in ranks if r and r <= k) / len(ranks)


def refused(o):
    return not o["sources"] and "outside that scope" in o["answer"]


def no_cite(o):
    return "[CITE:" not in o["answer"]


def agg(rows):
    n = len(rows)
    m = {"n": n}
    for key, lab in (("rank_exact", "exact"), ("rank_doc", "doc")):
        for k in (1, 5, 20):
            m[f"{lab}_recall@{k}"] = round(sum(frac_at(o[key], k) for o in rows) / n, 3)
        m[f"{lab}_mrr"] = round(sum(1 / min([r for r in o[key] if r] or [float("inf")]) for o in rows) / n, 3)
    js = [judge[o["question_id"]] for o in rows]
    m["answer_score"] = round(sum(j["correct"] for j in js) / (2 * n), 3)
    m["fully_correct"] = round(sum(j["correct"] == 2 for j in js) / n, 3)
    m["partly_correct"] = round(sum(j["correct"] == 1 for j in js) / n, 3)
    m["wrong_or_refused"] = round(sum(j["correct"] == 0 for j in js) / n, 3)
    m["cited_gold"] = round(sum(bool(j["cited_gold"]) for j in js) / n, 3)
    m["false_refusals"] = sum(refused(o) for o in rows)
    m["no_cite_markers"] = sum(no_cite(o) and not refused(o) and len(o["answer"].strip()) >= 20 for o in rows)
    m["empty_answers"] = sum(len(o["answer"].strip()) < 20 for o in rows)
    m["low_confidence_flagged"] = sum(bool(o["meta"].get("low_confidence")) for o in rows)
    m["avg_seconds"] = round(sum(o["t_total"] for o in rows) / n, 1)
    return m


rows = [run[q] for q in sorted(run)]
assert len(rows) == 200 and all(q in judge for q in run), "run/judge incomplete"
summary = {
    "setup": {"index": "badlaldh/singlaw-vdb @ aecbff97 (43,160 chunks)", "embedding": "Qwen/Qwen3-Embedding-0.6B (full profile)",
              "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2 (substituted: jina/Qwen3 reranker too slow on CPU)",
              "llm": llm, "judge": "Claude (manual, against gold answer + gold citations)",
              "exact": "gold Act section / judgment passage in top-k sources", "doc": "gold Act / judgment (any passage) in top-k sources"},
    "overall": agg(rows), "by_question_type": {}, "by_source_type": {},
}
for key, field in (("by_question_type", "question_type"), ("by_source_type", "source_type")):
    g = collections.defaultdict(list)
    for o in rows:
        g[o[field]].append(o)
    summary[key] = {k: agg(v) for k, v in sorted(g.items())}
temporal = [o["question_id"] for o in rows if re.match(r"As at (19|20)\d\d-12-31", o["answer"])]
summary["temporal_anchor_from_date_in_question"] = temporal
print(json.dumps(summary, indent=1))
json.dump(summary, open(os.path.join(b, f"{name}_summary{tag}.json"), "w", encoding="utf-8"), indent=2)
with open(os.path.join(b, f"{name}_results{tag}.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["question_id", "question_type", "source_type", "gold_exact_rank", "gold_doc_rank", "low_confidence",
                "judge_score", "cited_gold", "judge_note", "answer"])
    for o in rows:
        j = judge[o["question_id"]]
        w.writerow([o["question_id"], o["question_type"], o["source_type"],
                    "|".join(str(r) if r else "-" for r in o["rank_exact"]), "|".join(str(r) if r else "-" for r in o["rank_doc"]),
                    bool(o["meta"].get("low_confidence")), j["correct"], j["cited_gold"], j["note"], o["answer"]])

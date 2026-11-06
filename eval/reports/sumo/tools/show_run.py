"""Print run results next to the gold answer, for judging.
usage: python -I -X utf8 show_run.py <repo> <name> <from_idx> <to_idx>"""
import csv, json, sys, os, re
repo, name, lo, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
b = os.path.join(repo, "data", "export", "benchmark")
gold = {r["question_id"]: r for r in csv.DictReader(open(os.path.join(b, f"{name}.csv"), encoding="utf-8"))}
tag = ("_" + sys.argv[5]) if len(sys.argv) > 5 else ""
run = [json.loads(l) for l in open(os.path.join(b, f"{name}_run{tag}.jsonl"), encoding="utf-8") if l.strip()]
run.sort(key=lambda o: o["question_id"])
for o in [o for o in run if lo <= int(o["question_id"][-3:]) <= hi]:
    g = gold[o["question_id"]]
    ans = (o.get("answer") or "").replace("\n", " ")
    srcs = o.get("sources", [])
    used = sorted({int(n) for n in re.findall(r"\[CITE:(\d+)", o.get("answer") or "")})
    cites = [f"[{n}] {srcs[n-1]['chunk_id']}" for n in used if 0 < n <= len(srcs)]
    if not cites:
        cites = ["(no CITE) top3: " + ", ".join(s["chunk_id"] for s in srcs[:3])]
    print(f"=== {o['question_id']} [{g['question_type']}/{g['source_type']}] exact={o.get("rank_exact")} doc={o.get("rank_doc")} lowconf={o.get("meta",{}).get("low_confidence")} err={o.get('error')}")
    print("Q:", g["question"])
    print("GOLD:", g["answer"], "|| cites:", g["gold_citations"])
    print("SYS:", ans[:1400])
    print("SRC:", "; ".join(cites))

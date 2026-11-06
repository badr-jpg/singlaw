"""Build and validate data/export/benchmark/binyao.csv from q/b*.py.

usage: python -I -X utf8 build_csv.py <repo_root>
"""
import collections, csv, glob, json, os, re, runpy, sys

here = os.path.dirname(os.path.abspath(__file__))
repo = sys.argv[1]
name = "binyao"
allowed = set(open(os.path.join(repo, "eval", "benchmark_partition", f"{name}.txt"), encoding="utf-8").read().split())
T = json.load(open(os.path.join(here, "texts.json"), encoding="utf-8"))
texts, meta = T["texts"], T["meta"]

def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()

rows = []
for f in sorted(glob.glob(os.path.join(here, "q", "b*.py"))):
    rows.extend(runpy.run_path(f)["Q"])

out = []
for i, d in enumerate(rows, 1):
    out.append({
        "question_id": f"{name}-{i:03d}",
        "question": d["q"].strip(),
        "answer": d["a"].strip(),
        "question_type": d["t"],
        "source_type": d.get("s", "act"),
        "gold_doc_ids": "|".join(d["g"]),
        "gold_citations": "|".join(d["c"]),
        "evidence_quote": "|".join(d["e"]),
    })

# ---------------- validation ----------------
errs = []
if len(out) != 200:
    errs.append(f"row count {len(out)} != 200")
ids = [r["question_id"] for r in out]
if len(set(ids)) != len(ids):
    errs.append("duplicate question_id")
qs = collections.Counter(norm(r["question"]) for r in out)
errs += [f"duplicate question: {q[:60]}" for q, n in qs.items() if n > 1]

want_t = {"provision_lookup": 60, "lay_language": 60, "case_law": 40, "multi_hop": 40}
want_s = {"act": 100, "judgment": 70, "mixed": 30}
ct = collections.Counter(r["question_type"] for r in out)
cs = collections.Counter(r["source_type"] for r in out)
if dict(ct) != want_t: errs.append(f"type counts {dict(ct)}")
if dict(cs) != want_s: errs.append(f"source counts {dict(cs)}")

def docgroup(g):  # judgment passages group to their judgment
    return meta[g]["citation"] if meta.get(g, {}).get("kind") == "judgment" else g

per_doc = collections.Counter()
for r in out:
    g = r["gold_doc_ids"].split("|"); c = r["gold_citations"].split("|"); e = r["evidence_quote"].split("|")
    if not (len(g) == len(c) == len(e)):
        errs.append(f"{r['question_id']}: list lengths differ"); continue
    kinds = set()
    for gi, ei in zip(g, e):
        if gi not in allowed: errs.append(f"{r['question_id']}: {gi} not in {name}.txt")
        if gi not in texts: errs.append(f"{r['question_id']}: {gi} has no text"); continue
        if norm(ei) not in norm(texts[gi]): errs.append(f"{r['question_id']}: quote not verbatim in {gi}")
        if len(ei.split()) > 40: errs.append(f"{r['question_id']}: quote > 40 words")
        kinds.add(meta[gi]["kind"])
    for grp in set(docgroup(x) for x in g):
        per_doc[grp] += 1
    st = r["source_type"]
    if st == "mixed" and len(set(g)) < 2: errs.append(f"{r['question_id']}: mixed needs >=2 docs")
    if st in ("act", "judgment") and kinds != {"legislation" if st == "act" else "judgment"} and kinds != {st}:
        errs.append(f"{r['question_id']}: source_type {st} vs kinds {kinds}")
    if r["question_type"] == "lay_language" and re.search(r"\bAct\b|\[\d{4}\]| v ", r["question"]):
        errs.append(f"{r['question_id']}: lay_language names an Act/case")
    n_sent = len(re.findall(r"[.!?](?:\s|$)", r["answer"]))
    if not 1 <= n_sent <= 3: errs.append(f"{r['question_id']}: answer has {n_sent} sentences")
over = {k: v for k, v in per_doc.items() if v > 12}
if over: errs.append(f"docs over 12 questions: {over}")
if len(per_doc) < 40: errs.append(f"only {len(per_doc)} documents covered")

print("rows", len(out)); print("question_type", dict(ct)); print("source_type", dict(cs))
print("documents covered", len(per_doc), "| max per doc", per_doc.most_common(3))
used_ids = {x for r in out for x in r["gold_doc_ids"].split("|")}
acts_used = {x for x in used_ids if meta[x]["kind"] != "judgment"}
cases_used = {meta[x]["citation"] for x in used_ids if meta[x]["kind"] == "judgment"}
n_acts = sum(1 for x in allowed if meta.get(x, {}).get("kind") != "judgment")
n_cases = len({meta[x]["citation"] for x in allowed if meta.get(x, {}).get("kind") == "judgment"})
print(f"acts used {len(acts_used)}/{n_acts}, judgments used {len(cases_used)}/{n_cases}, passages used {len(used_ids)}")
if errs:
    print("VALIDATION FAILED"); [print(" -", e) for e in errs]; sys.exit(1)

dst = os.path.join(repo, "data", "export", "benchmark"); os.makedirs(dst, exist_ok=True)
path = os.path.join(dst, f"{name}.csv")
with open(path, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
# re-read the written file and check it round-trips
back = list(csv.DictReader(open(path, encoding="utf-8")))
assert back == out, "CSV round-trip mismatch"
print("VALIDATION PASSED ->", path)
with open(os.path.join(here, "unused_docs.txt"), "w", encoding="utf-8") as fh:
    for x in sorted(allowed):
        m = meta.get(x, {})
        key = m.get("citation") if m.get("kind") == "judgment" else x
        if (m.get("kind") == "judgment" and key not in cases_used) or (m.get("kind") != "judgment" and x not in acts_used):
            fh.write(f"{x}\t{m.get('title') or m.get('case_name','')}\n")

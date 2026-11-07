"""Inter-annotator agreement for the haotien partition, following eval/scripts/final_agreement.py
(same pairwise Cohen's kappa, Fleiss' kappa, majority vote and "clean" definition). Items in fix/
were first shown with another section's text (a generic quote matched the wrong section) and were
re-annotated by all three annotators with the correct section; those labels replace the first pass.
usage: python haotien_agreement.py <judged.jsonl> <out_dir>"""
import collections, csv, glob, itertools, json, sys
from pathlib import Path

A = Path(__file__).resolve().parent
judged_path, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

def load(root):
    L = {a: {} for a in "ABC"}
    for a in L:
        for f in glob.glob(str(root / a / "out" / "*.jsonl")):
            for l in open(f, encoding="utf-8"):
                if l.strip():
                    d = json.loads(l)
                    L[a][d["id"]] = d
    return L

first = load(A)
fix = load(A / "fix")  # correction pass: items first shown with a different section's text
fixed = set(fix["A"])
assert fixed == set(fix["B"]) == set(fix["C"])
L = {a: {**first[a], **fix[a]} for a in "ABC"}
ids = sorted(L["A"])
assert set(ids) == set(L["B"]) == set(L["C"]) and len(ids) == 200, {a: len(v) for a, v in L.items()}

def fleiss(rows, cats):
    n, N = 3, len(rows)
    P = [(sum(r.count(c) ** 2 for c in cats) - n) / (n * (n - 1)) for r in rows]
    pb = sum(P) / N
    pc = [sum(r.count(c) for r in rows) / (N * n) for c in cats]
    pe = sum(x * x for x in pc)
    return (pb - pe) / (1 - pe) if pe < 1 else 1.0

def kap(x, y, cats):
    N = len(x)
    po = sum(a == b for a, b in zip(x, y)) / N
    pe = sum(x.count(c) / N * y.count(c) / N for c in cats)
    return po, ((po - pe) / (1 - pe) if pe < 1 else 1.0)

def stats(ids, L=L):
    o = {}
    for k, cats in [("reference_label", ["correct", "partial", "incorrect"]), ("answerable", ["yes", "no"]), ("standalone", ["yes", "no"])]:
        rows = [[L[a][i][k] for a in "ABC"] for i in ids]
        pair = {}
        for a, b in itertools.combinations("ABC", 2):
            po, kp = kap([L[a][i][k] for i in ids], [L[b][i][k] for i in ids], cats)
            pair[a + b] = {"agreement": round(po, 4), "cohen_kappa": round(kp, 4)}
        o[k] = {"pairwise": pair,
                "mean_pairwise_agreement": round(sum(v["agreement"] for v in pair.values()) / 3, 4),
                "all_three_agree": round(sum(len(set(r)) == 1 for r in rows) / len(rows), 4),
                "fleiss_kappa": round(fleiss(rows, cats), 4),
                "counts": {a: dict(collections.Counter(L[a][i][k] for i in ids)) for a in "ABC"}}
    return o

out = {"n": len(ids), "items_reannotated": len(fixed), "reannotated_ids": sorted(fixed),
       "final": stats(ids), "first_pass": stats(ids, first)}
final = []
for i in ids:
    r = {"question_id": i, "person": "haotien", "reannotated_with_correct_section": i in fixed}
    for k in ("reference_label", "answerable", "standalone"):
        v = [L[a][i][k] for a in "ABC"]
        c = collections.Counter(v).most_common(1)[0]
        r[k] = c[0] if c[1] >= 2 else "disputed"
        r[k + "_votes"] = "/".join(v)
    r["notes"] = " | ".join(f"{a}: {L[a][i]['note']}" for a in "ABC" if (L[a][i].get("note") or "").strip())
    final.append(r)
with open(OUT / "haotien_annotation_labels.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, list(final[0].keys()))
    w.writeheader()
    w.writerows(final)

score = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}
J = {d["question_id"]: d for d in map(json.loads, open(judged_path, encoding="utf-8")) if d}
mean = lambda q: round(sum(score[J[x]["correctness"]] for x in q) / len(q), 4) if q else None
m = {k: dict(collections.Counter(r[k] for r in final)) for k in ("reference_label", "answerable", "standalone")}
clean = [r["question_id"] for r in final if r["reference_label"] == "correct" and r["answerable"] == "yes" and r["standalone"] == "yes"]
out["majority"] = m
out["clean_items"] = len(clean)
out["singlaw_correctness"] = {"all_200": mean(ids), "clean_items": mean(clean),
                              **{f"label_{k}": (mean([r["question_id"] for r in final if r["reference_label"] == k]),
                                                sum(r["reference_label"] == k for r in final)) for k in m["reference_label"]}}
types = {d["question_id"]: d["question_type"] for d in J.values()}
out["by_question_type"] = {t: {k: dict(collections.Counter(r[k] for r in final if types[r["question_id"]] == t))
                               for k in ("reference_label", "answerable", "standalone")} for t in sorted(set(types.values()))}
out["flagged_incorrect"] = [r["question_id"] for r in final if r["reference_label"] == "incorrect"]
out["flagged_partial"] = [r["question_id"] for r in final if r["reference_label"] == "partial"]
out["flagged_not_standalone"] = [r["question_id"] for r in final if r["standalone"] == "no"]
out["flagged_not_answerable"] = [r["question_id"] for r in final if r["answerable"] == "no"]
out["disputed"] = [r["question_id"] for r in final if "disputed" in (r["reference_label"], r["answerable"], r["standalone"])]
out["partial_unanimous"] = sum(r["reference_label_votes"] == "partial/partial/partial" for r in final)
(OUT / "haotien_agreement.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

f = out["final"]
for k in f:
    print(f"{k:<16} mean pairwise {f[k]['mean_pairwise_agreement']:.3f}  all three {f[k]['all_three_agree']:.3f}  Fleiss {f[k]['fleiss_kappa']:.3f}  counts {f[k]['counts']}")
print(json.dumps({k: out[k] for k in ("majority", "clean_items", "singlaw_correctness", "partial_unanimous")}))
for k in ("flagged_incorrect", "flagged_partial", "flagged_not_standalone", "flagged_not_answerable", "disputed"):
    print(k, out[k])

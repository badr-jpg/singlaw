"""Recompute gold targets and rank_exact for a run file, handling subsection-style
Act citations ('s 3(1)', 'ss 3(2) and 4', 's 4(1)-(2)', 's 7 (Rule 2)', 'ss 4-5').
usage: python fix_exact.py <repo> <name> <tag>   (rewrites <name>_run_<tag>.jsonl in place)"""
import csv, json, re, sqlite3, sys
from pathlib import Path

def act_sections(cite: str) -> list[str]:
    secs = re.sub(r"\s*\(Rules?[^)]*\)", "", re.sub(r"^.*?,\s*ss?\s+", "", cite))
    nums = []
    for piece in re.split(r",\s*|\s+and\s+", secs):
        piece = piece.strip()
        m = re.match(r"^(\d+)[–-](\d+)$", piece)
        if m:
            nums += [str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1)]
            continue
        m = re.match(r"^(\d+[A-Z]*)", piece)
        if m and m.group(1) not in nums:
            nums.append(m.group(1))
    return nums

def gold_targets(r, slug_by_cite):
    out = []
    for g, c in zip(r["gold_doc_ids"].split("|"), r["gold_citations"].split("|")):
        m = re.match(r"(\d{4})_(SG[A-Z]+)_(\d+)-(\d+)$", g)
        if m:
            y, court, num, part = m.groups()
            slug = slug_by_cite.get(f"[{y}] {court.replace('SGHCA', 'SGHC(A)')} {num}")
            out.append({"gold": g, "doc": slug, "exact": [f"{slug}:part{int(part)}"], "kind": "judgment"})
        else:
            out.append({"gold": g, "doc": g, "exact": [f"{g}:s{n}" for n in act_sections(c)], "kind": "act"})
    return out

def first_rank(pred, items):
    for i, x in enumerate(items, 1):
        if pred(x):
            return i
    return None

if __name__ == "__main__":
    repo, name, tag = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    b = repo / "data" / "export" / "benchmark"
    rows = {r["question_id"]: r for r in csv.DictReader(open(b / f"{name}.csv", encoding="utf-8"))}
    slug = dict(sqlite3.connect(repo / "data" / "db" / "app.sqlite3").execute("select citation, doc_id from judgments"))
    p = b / f"{name}_run_{tag}.jsonl"
    runs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    changed = 0
    for o in runs:
        if "sources" not in o:
            continue
        t = gold_targets(rows[o["question_id"]], slug)
        cids = [s.get("chunk_id") or "" for s in o["sources"]]
        docs = [c.split(":", 1)[0] for c in cids]
        re_ = [first_rank(lambda c, t=x: any(c == e or c.startswith(e + ".") for e in t["exact"]), cids) for x in t]
        rd = [first_rank(lambda d, t=x: d == t["doc"], docs) for x in t]
        changed += re_ != o.get("rank_exact")
        o["gold"], o["rank_exact"], o["rank_doc"] = t, re_, rd
    p.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in runs), encoding="utf-8")
    print(f"{len(runs)} rows, rank_exact changed for {changed}")

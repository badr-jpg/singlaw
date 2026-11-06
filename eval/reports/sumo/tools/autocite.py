"""cited_gold helper: does any [CITE:n] point at a gold section / gold passage (or passage ±1)?
usage: python -I -X utf8 autocite.py <bench_dir> <run.jsonl> [ids...]"""
import json, re, sys
b, f = sys.argv[1], sys.argv[2]; want = set(sys.argv[3:])
def hit(cid, t):
    for e in t["exact"]:
        if cid == e or cid.startswith(e + "."):
            return True
        if t["kind"] == "judgment":
            m = re.match(r"(.*):part(\d+)$", e); m2 = re.match(r"(.*):part(\d+)$", cid)
            if m and m2 and m.group(1) == m2.group(1) and abs(int(m.group(2)) - int(m2.group(2))) <= 1:
                return True
    return False
out = {}
for o in map(json.loads, open(f"{b}/{f}", encoding="utf-8")):
    q = o["question_id"]
    if want and q[-3:] not in want: continue
    used = {int(n) for n in re.findall(r"\[CITE:(\d+)", o.get("answer") or "")}
    cids = [o["sources"][n-1]["chunk_id"] for n in used if 0 < n <= len(o["sources"])]
    out[q] = any(hit(c, t) for c in cids for t in o["gold"])
print(json.dumps(out))

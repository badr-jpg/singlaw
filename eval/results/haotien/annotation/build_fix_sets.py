"""Correction pass: rebuild evidence for items whose source text came from the wrong section,
picking the chunk whose citation matches the gold section. Writes fix/{A,B,C}/batch_00.txt + manifest.
usage: python build_fix_sets.py <bench_dir> <annot_dir> <id> [<id> ...]"""
import csv, json, random, re, sys
from pathlib import Path
from qdrant_client import QdrantClient

bench, ANN, ids = Path(sys.argv[1]), Path(sys.argv[2]), set(sys.argv[3:])
OUT = ANN / "fix"
keys = json.load(open(bench / "haotien.gold_index_keys.json", encoding="utf-8"))
client = QdrantClient(path=str(Path.home() / "singlaw/data/qdrant"))
by_doc, off = {}, None
while True:
    pts, off = client.scroll("sg_law", limit=5000, offset=off,
                             with_payload=["doc_id", "citation", "text"], with_vectors=False)
    for p in pts:
        by_doc.setdefault(p.payload["doc_id"], []).append((p.payload["citation"], p.payload.get("text") or ""))
    if off is None:
        break
client.close()

sq = lambda s: re.sub(r"\s+", "", s or "")
def locate(gold_id, cite, q):
    m = re.search(r",\s*(?:s|Art|ss)\s*(\d+[A-Z]*)", cite)
    want = f"s {m.group(1)}" if m else None
    chunks = by_doc[keys[gold_id]["doc_id"]]
    hits = [(c, t) for c, t in chunks if sq(q) in sq(t)]
    right = [(c, t) for c, t in hits if want and re.search(rf",\s*{re.escape(want)}(\s|$|\()", c)]
    c, t = (right or hits)[0]
    if len(t) > 3000:
        mm = re.search(r"\s*".join(map(re.escape, sq(q))), t)
        a = max(0, mm.start() - 1200) if mm else 0
        t = t[a:a + 3000]
    return c, t

items = []
for r in csv.DictReader(open(bench / "haotien.csv", encoding="utf-8-sig", newline="")):
    if r["question_id"] not in ids:
        continue
    ev = []
    for d, c, q in zip(r["gold_doc_ids"].split("|"), r["gold_citations"].split("|"), r["evidence_quote"].split("|")):
        src, t = locate(d, c, q)
        print(r["question_id"], "cited", c, "-> source chunk", src)
        ev.append({"citation": c, "quote": q, "source_text": t})
    items.append({"id": r["question_id"], "question": r["question"], "reference_answer": r["answer"], "evidence": ev})
assert len(items) == len(ids)

man = {}
for ann, seed in [("A", 101), ("B", 202), ("C", 303)]:
    d = OUT / ann
    (d / "out").mkdir(parents=True, exist_ok=True)
    x = items[:]
    random.Random(seed).shuffle(x)
    (d / "batch_00.txt").write_text("\n\n".join(
        "### ITEM " + i["id"] + "\nQUESTION: " + i["question"] + "\nREFERENCE ANSWER: " + i["reference_answer"] + "\n" +
        "\n".join(f"EVIDENCE [{e['citation']}]\nQUOTE: {e['quote']}\nSOURCE TEXT: {e['source_text']}" for e in i["evidence"])
        for i in x), encoding="utf-8")
    man[ann] = {"00": [i["id"] for i in x]}
(OUT / "manifest.json").write_text(json.dumps(man))
print(man)

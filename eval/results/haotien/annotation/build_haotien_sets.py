"""Blind annotation batches for the haotien partition, mirroring eval/scripts/build_sets.py:
3 annotators (seeds 101/202/303), batches of 80, evidence = quote + up to 3,000 chars of the
index chunk that holds it. No system answers or judge scores.
usage: python build_haotien_sets.py <bench_dir> <out_dir>"""
import csv, json, random, re, sys
from pathlib import Path
from qdrant_client import QdrantClient

bench, OUT = Path(sys.argv[1]), Path(sys.argv[2])
keys = json.load(open(bench / "haotien.gold_index_keys.json", encoding="utf-8"))
client = QdrantClient(path=str(Path.home() / "singlaw/data/qdrant"))
by_doc, by_cite, off = {}, {}, None
while True:
    pts, off = client.scroll("sg_law", limit=5000, offset=off,
                             with_payload=["doc_id", "citation", "text"], with_vectors=False)
    for p in pts:
        t = p.payload.get("text") or ""
        by_doc.setdefault(p.payload["doc_id"], []).append(t)
        by_cite.setdefault(p.payload["citation"], []).append(t)
    if off is None:
        break
client.close()

sq = lambda s: re.sub(r"\s+", "", s or "")
def locate(gold_id, q):
    k = keys[gold_id]
    cands = by_doc.get(k["doc_id"], []) if "doc_id" in k else by_cite.get(k["citation"], [])
    qs = sq(q)
    for t in cands:
        if qs and qs in sq(t):
            if len(t) <= 3000:
                return t, True
            m = re.search(r"\s*".join(map(re.escape, qs)), t)
            if m:
                a = max(0, m.start() - 1200)
                return t[a:a + 3000], True
            return t[:3000], True
    return (cands[0][:1500] if len(cands) == 1 else ""), False

rows = list(csv.DictReader(open(bench / "haotien.csv", encoding="utf-8-sig", newline="")))
items, nf = [], 0
for r in rows:
    ev = []
    for d, c, q in zip(r["gold_doc_ids"].split("|"), r["gold_citations"].split("|"), r["evidence_quote"].split("|")):
        t, found = locate(d, q)
        nf += not found
        ev.append({"citation": c, "quote": q, "source_text": t})
    items.append({"id": r["question_id"], "question": r["question"], "reference_answer": r["answer"], "evidence": ev})
print("items", len(items), "quotes without surrounding text", nf)

SIZE, man = 80, {}
for ann, seed in [("A", 101), ("B", 202), ("C", 303)]:
    d = OUT / ann
    (d / "out").mkdir(parents=True, exist_ok=True)
    x = items[:]
    random.Random(seed).shuffle(x)
    bs = [x[i:i + SIZE] for i in range(0, len(x), SIZE)]
    for n, b in enumerate(bs):
        (d / f"batch_{n:02d}.txt").write_text("\n\n".join(
            "### ITEM " + i["id"] + "\nQUESTION: " + i["question"] + "\nREFERENCE ANSWER: " + i["reference_answer"] + "\n" +
            "\n".join(f"EVIDENCE [{e['citation']}]\nQUOTE: {e['quote']}\nSOURCE TEXT: {e['source_text'] or '(only the quote is available)'}"
                      for e in i["evidence"]) for i in b), encoding="utf-8")
    man[ann] = {f"{n:02d}": [i["id"] for i in b] for n, b in enumerate(bs)}
(OUT / "manifest.json").write_text(json.dumps(man))
print({k: {b: len(v) for b, v in bs.items()} for k, bs in man.items()})

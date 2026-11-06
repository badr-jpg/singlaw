"""Check a labelled benchmark CSV against the pinned source datasets.

    cd backend && uv run --with pandas --with pyarrow --with huggingface_hub \
        python ../eval/validate_benchmark_pinned.py darien

Confirms, as eval/build_eval.md requires:
  - exactly 200 rows, no duplicate questions, and the required mix
    (100 Act / 70 judgment / 30 multi-document; 60 provision_lookup,
    60 lay_language, 40 case_law, 40 multi_hop; <=12 per document;
    >=40 documents covered)
  - every gold_doc_id is in eval/benchmark_partition/<name>.txt
  - every evidence_quote appears word for word in its gold document,
    ignoring whitespace

Sources (downloaded from the Hugging Face Hub at the pinned revisions unless
local copies are given with --judgments / --sections):
  badlaldh/singapore-judgments @ 290e968  data/train-00000-of-00001.parquet
  Kaidon-Ng/singapore-statutes @ 8b81a0c  data/sections.parquet
Exit code 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PART_DIR = ROOT / "eval" / "benchmark_partition"
JUDGMENTS = ("badlaldh/singapore-judgments", "290e968", "data/train-00000-of-00001.parquet")
SECTIONS = ("Kaidon-Ng/singapore-statutes", "8b81a0c", "data/sections.parquet")

TYPES = {"provision_lookup": 60, "lay_language": 60, "case_law": 40, "multi_hop": 40}
COLUMNS = ["question_id", "question", "answer", "question_type", "source_type",
           "gold_doc_ids", "gold_citations", "evidence_quote"]
LAY_FORBIDDEN = re.compile(r"\b(act|section)\b|\bs \d|\[\d{4}\]|\bsghc|\bsgca", re.I)


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def read_rows(path: str) -> list[dict]:
    """Rows of a .parquet or .jsonl file as dicts."""
    if path.endswith(".jsonl"):
        return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    import pandas as pd
    return pd.read_parquet(path).to_dict("records")


def fetch(spec: tuple[str, str, str], local: str | None) -> str:
    if local:
        return local
    from huggingface_hub import hf_hub_download
    repo, rev, fn = spec
    return hf_hub_download(repo, fn, repo_type="dataset", revision=rev)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="lowercase name used in eval/benchmark_partition/")
    ap.add_argument("--csv", help="default: data/export/benchmark/<name>.csv")
    ap.add_argument("--judgments", help="local judgments .parquet (or .jsonl)")
    ap.add_argument("--sections", help="local sections .parquet (or .jsonl)")
    a = ap.parse_args()

    csv_path = Path(a.csv or ROOT / "data" / "export" / "benchmark" / f"{a.name}.csv")
    ids = set((PART_DIR / f"{a.name}.txt").read_text().split())
    person = json.loads((PART_DIR / "partition.json").read_text())["people"][a.name]
    acts = {x["doc_id"]: x for x in person["acts"]}

    errs: list[str] = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            errs.append(f"header is {reader.fieldnames}, expected {COLUMNS}")
        rows = list(reader)

    # ---- source texts, keyed by gold doc id ----
    needed = {d for r in rows for d in r["gold_doc_ids"].split("|")}
    texts: dict[str, str] = {}
    sec_rows = read_rows(fetch(SECTIONS, a.sections))
    for d in needed & set(acts):
        lo, hi = acts[d]["source_rows"]
        texts[d] = " ".join(str(r.get("text") or "") for r in sec_rows[lo:hi + 1])
    for r in read_rows(fetch(JUDGMENTS, a.judgments)):
        did = str(r.get("doc_id"))
        if did not in needed and r.get("part") is not None:
            did = f"{did}-{int(r['part']):04d}"
        if did in needed:
            texts[did] = str(r.get("text") or "")
    texts = {k: squash(v) for k, v in texts.items()}

    # ---- row checks ----
    if len(rows) != 200:
        errs.append(f"{len(rows)} rows, expected 200")
    dup = [q for q, n in Counter(r["question"].strip().lower() for r in rows).items() if n > 1]
    errs += [f"duplicate question: {q}" for q in dup]
    want_ids = [f"{a.name}-{i:03d}" for i in range(1, len(rows) + 1)]
    if [r["question_id"] for r in rows] != want_ids:
        errs.append("question_id values are not <name>-001 .. in order")

    per_doc: Counter = Counter()
    mix: Counter = Counter()
    for r in rows:
        qid, golds = r["question_id"], r["gold_doc_ids"].split("|")
        quotes, cites = r["evidence_quote"].split("|"), r["gold_citations"].split("|")
        if r["question_type"] not in TYPES:
            errs.append(f"{qid}: bad question_type {r['question_type']}")
        if not r["answer"].strip():
            errs.append(f"{qid}: empty answer")
        if len(quotes) != len(golds) or len(cites) != len(golds):
            errs.append(f"{qid}: {len(golds)} gold ids, {len(cites)} citations, {len(quotes)} quotes")
        kinds = {"act" if g in acts else "judgment" for g in golds}
        expect_st = "mixed" if len(kinds) > 1 else kinds.pop()
        if r["source_type"] != expect_st:
            errs.append(f"{qid}: source_type {r['source_type']}, expected {expect_st}")
        mix["multi" if len(set(golds)) > 1 else expect_st] += 1
        if r["question_type"] == "lay_language" and LAY_FORBIDDEN.search(r["question"]):
            errs.append(f"{qid}: lay_language question names an Act, section or case")
        for g, q in zip(golds, quotes):
            per_doc[g] += 1
            if g not in ids:
                errs.append(f"{qid}: {g} is not in {a.name}.txt")
            elif g not in texts:
                errs.append(f"{qid}: {g} not found in the source dataset")
            elif len(q.split()) > 40:
                errs.append(f"{qid}: quote for {g} is over 40 words")
            elif squash(q) not in texts[g]:
                errs.append(f"{qid}: quote not found in {g}: {q[:60]}…")

    types = Counter(r["question_type"] for r in rows)
    for t, n in TYPES.items():
        if types[t] != n:
            errs.append(f"{types[t]} {t} questions, expected {n}")
    for k, n in {"act": 100, "judgment": 70, "multi": 30}.items():
        if mix[k] != n:
            errs.append(f"{mix[k]} {k} questions, expected {n}")
    errs += [f"{d} is used by {n} questions (max 12)" for d, n in per_doc.items() if n > 12]
    if len(per_doc) < 40:
        errs.append(f"only {len(per_doc)} documents covered, need 40")

    print(f"rows {len(rows)} | types {dict(types)} | single-act {mix['act']} "
          f"single-judgment {mix['judgment']} multi-doc {mix['multi']} | "
          f"documents covered {len(per_doc)} of {len(ids)}")
    for e in errs:
        print("FAIL", e)
    print("OK — all checks passed" if not errs else f"{len(errs)} problem(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())

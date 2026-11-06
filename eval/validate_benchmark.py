"""Validate a labelled benchmark CSV against the rules in eval/build_eval.md.

    cd backend && uv run --with pandas --with pyarrow python ../eval/validate_benchmark.py <name> \
        --sections <sections.parquet> --judgments <train-00000-of-00001.parquet>

Checks: 200 rows, no duplicate questions, the type/source mix, <=12 rows per
document, >=40 documents, every gold_doc_id in eval/benchmark_partition/<name>.txt,
and every evidence_quote appearing word for word (whitespace-insensitive) in its
gold document. Acts are loaded by their source_rows range, never by name.
Exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PART = ROOT / "eval" / "benchmark_partition"
WANT_TYPES = {"provision_lookup": 60, "lay_language": 60, "case_law": 40, "multi_hop": 40}
WANT_SOURCES = {"act": 100, "judgment": 70, "mixed": 30}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--sections", type=Path, required=True)
    ap.add_argument("--judgments", type=Path, required=True)
    a = ap.parse_args()

    path = a.csv or ROOT / "data" / "export" / "benchmark" / f"{a.name}.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    ids = set((PART / f"{a.name}.txt").read_text().split())
    person = json.loads((PART / "partition.json").read_text())["people"][a.name]

    sections = pd.read_parquet(a.sections)
    docs: dict[str, str] = {}
    for act in person["acts"]:
        lo, hi = act["source_rows"]
        docs[act["doc_id"]] = norm(" ".join(sections.iloc[lo:hi + 1]["text"]))
    judg = pd.read_parquet(a.judgments).set_index("doc_id")

    def text(doc_id: str) -> str:
        if doc_id not in docs:
            docs[doc_id] = norm(judg.loc[doc_id, "text"])
        return docs[doc_id]

    errs: list[str] = []
    if len(rows) != 200:
        errs.append(f"{len(rows)} rows, want 200")
    dupes = [q for q, n in Counter(norm(r["question"]).lower() for r in rows).items() if n > 1]
    errs += [f"duplicate question: {q}" for q in dupes]
    types = dict(Counter(r["question_type"] for r in rows))
    sources = dict(Counter(r["source_type"] for r in rows))
    if types != WANT_TYPES:
        errs.append(f"question_type mix {types}")
    if sources != WANT_SOURCES:
        errs.append(f"source_type mix {sources}")

    per_doc: Counter[str] = Counter()
    for r in rows:
        qid = r["question_id"]
        gold = r["gold_doc_ids"].split("|")
        cites = r["gold_citations"].split("|")
        quotes = r["evidence_quote"].split("|")
        if not (len(gold) == len(cites) == len(quotes)):
            errs.append(f"{qid}: gold_doc_ids/gold_citations/evidence_quote lengths differ")
        if r["source_type"] == "mixed" and len(set(gold)) < 2:
            errs.append(f"{qid}: mixed row needs two or more documents")
        per_doc.update(set(gold))
        for doc_id, quote in zip(gold, quotes):
            if doc_id not in ids:
                errs.append(f"{qid}: {doc_id} not in {a.name}.txt")
                continue
            if len(quote.split()) > 40:
                errs.append(f"{qid}: quote over 40 words")
            if norm(quote) not in text(doc_id):
                errs.append(f"{qid}: quote not found in {doc_id}: {quote[:60]}")
    errs += [f"{d}: {n} rows (max 12)" for d, n in per_doc.items() if n > 12]
    if len(per_doc) < 40:
        errs.append(f"only {len(per_doc)} documents covered (min 40)")

    print(f"rows={len(rows)} types={types} sources={sources}")
    print(f"documents covered={len(per_doc)} max rows per document={max(per_doc.values())}")
    for e in errs:
        print("FAIL", e)
    print("OK" if not errs else f"{len(errs)} failure(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())

"""Check the SSO parser against a real page you saved by hand.

    cd backend
    uv run python ../scripts/check_parse.py ~/Downloads/EmA1968.html
    uv run python ../scripts/check_parse.py page.html --kind judgment

Prints what the parser extracted (title, status, sections, residue) and how it
chunks, so selector problems show up before the 05:00 crawl. Saving a page in
a browser is ordinary browsing, not automated extraction.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ingest.archive import read_archived  # noqa: E402
from app.ingest.chunker import chunk_judgment, chunk_legislation  # noqa: E402
from app.ingest.judgment_parser import parse_judgment  # noqa: E402
from app.ingest.sso_parser import parse_legislation  # noqa: E402


def show_chunks(chunks) -> None:
    sizes = [len(c.text) for c in chunks]
    print(f"\nchunks: {len(chunks)}")
    if sizes:
        print(f"chunk chars: mean {statistics.mean(sizes):.0f}, "
              f"median {statistics.median(sizes):.0f}, max {max(sizes)}")
        c = chunks[0]
        print(f"\nfirst chunk citation: {c.citation}")
        print(f"context: {c.context}")
        print(f"text: {c.text[:300]}…")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path)
    ap.add_argument("--kind", choices=["legislation", "judgment"], default="legislation")
    args = ap.parse_args()
    html = read_archived(args.html)

    if args.kind == "judgment":
        j = parse_judgment(html)
        print(f"citation: {j.neutral_citation!r}  case: {j.case_name!r}")
        print(f"court: {j.court} (level {j.court_level})  decided: {j.decision_date}")
        print(f"paragraphs: {len(j.paragraphs)}  cites: {len(j.cites)}")
        for p in j.paragraphs[:3]:
            print(f"  [{p.number}] {p.text[:120]}")
        show_chunks(chunk_judgment(j))
        return

    doc = parse_legislation(html)
    secs = doc.sections()
    print(f"title: {doc.title!r}")
    print(f"doc_type: {doc.doc_type}  status: {doc.status}  version: {doc.sso_version_date}")
    print(f"sections parsed: {len(secs)}")
    for s in secs[:5]:
        print(f"  s {s.number} — {s.heading!r}: {s.text[:90]!r}")
    if len(secs) > 5:
        print(f"  … last: s {secs[-1].number} — {secs[-1].heading!r}")
    print(f"unparsed residue lines: {len(doc.unparsed)}")
    for line in doc.unparsed[:8]:
        print(f"  ? {line[:120]}")
    show_chunks(chunk_legislation(doc))

    problems = []
    if not doc.title:
        problems.append("no title found")
    if len(secs) < 3:
        problems.append("fewer than 3 sections: selectors or lazy loading?")
    if secs and len(doc.unparsed) > len(secs):
        problems.append("more residue lines than sections")
    print("\nVERDICT:", "OK" if not problems else "CHECK — " + "; ".join(problems))


if __name__ == "__main__":
    main()

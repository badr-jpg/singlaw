"""Export the eLitigation raw archive as a private Hugging Face dataset.

    uv run --with pyarrow python -m app.hf_export build
    uv run --with pyarrow python -m app.hf_export subset
    uv run --with pyarrow python -m app.hf_export upload --repo <user>/<name>

`build` parses every archived page into Parquet shards plus a dataset card and
never touches the network. `upload` only ever writes to a private repo: it
checks visibility before and after the upload, and stops if the repo is public.
Raw HTML is left out because it still contains the masked ID numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.ingest.judgment_parser import parse_elitigation_judgment

SHARD_ROWS = 1000
# NRIC/FIN shape, including spaced and hyphenated forms and re-cased titles. Older
# charges print them beside the accused's name. Trade mark numbers share the
# shape, so those are recognised by what precedes them.
_ID_RX = re.compile(r"\b[STFG][\s./-]?\d{7,8}[\s./-]?[A-Z]\b", re.IGNORECASE)
_NOT_ID_RX = re.compile(r"(trade\s*marks?|\bTM\b|application|registration)[^.]{0,40}$",
                        re.IGNORECASE)
# Labelled numbers in other shapes: old-style ICs and passports
_LABELLED_ID_RX = re.compile(
    r"(?<![A-Za-z])((?:[Nn][Rr][Ii][Cc]|FIN|[Ii]/?[Cc]|[Pp]assport(?:\s+(?:bearing|with|the|serial|passport)){0,4}"
    r"|Identity Card)"
    r"(?:\s*(?:No|Nos|[Nn]umber)\.?)?[\s:.,)]*\"?)"
    r"((?:[A-Za-z]{1,3}[\s-]?)?\d[\d\s-]{3,10}\d(?:[\s/-]?[A-Z])?\b)")
MASK = "[ID NUMBER REMOVED]"


class PublicRepoError(RuntimeError):
    """The target repo is not private, so nothing may be uploaded to it."""


def mask_ids(text: str) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        if _NOT_ID_RX.search(text[max(0, m.start() - 60):m.start()]):
            return m.group(0)
        count += 1
        return MASK

    text = _ID_RX.sub(sub, text)

    def labelled(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(1) + MASK

    return _LABELLED_ID_RX.sub(labelled, text), count


def build_row(rec: dict, html: str) -> dict[str, Any]:
    """One dataset row from a manifest record and its archived page."""
    url = f"https://www.elitigation.sg/gd/s/{rec['slug']}"
    j = parse_elitigation_judgment(html, entry=rec, source_url=url)
    masked = 0
    paragraphs = []
    for p in j.paragraphs:
        body, n = mask_ids(p.text)
        masked += n
        paragraphs.append({"number": p.number, "text": body})
    disposition, _ = mask_ids(j.disposition) if j.disposition else (None, 0)
    case_name, n = mask_ids(j.case_name)  # estate cases print the deceased's ID in the title
    masked += n
    label = (lambda p: f"[{p['number']}] {p['text']}") if j.numbered else (lambda p: p["text"])
    return {
        "slug": rec["slug"],
        "citation": j.neutral_citation,
        "case_name": case_name,
        "case_number": rec.get("case_number") or None,
        "court_code": j.court_code,
        "court": j.court,
        "court_level": j.court_level,
        "year": rec["year"],
        "decision_date": j.decision_date.isoformat() if j.decision_date else None,
        "coram": j.coram,
        "catchwords": j.catchwords,
        "disposition": disposition,
        "paragraphs_numbered": j.numbered,
        "paragraphs": paragraphs,
        "text": "\n\n".join(label(p) for p in paragraphs),
        "cites": j.cites,
        "source_url": url,
        "fetched_at": rec.get("fetched_at"),
        "ids_masked": masked,
    }


def _row_from_paths(args: tuple[dict, str]) -> dict[str, Any]:
    rec, path = args
    return build_row(rec, Path(path).read_text(encoding="utf-8"))


def _manifest(archive: Path) -> list[dict]:
    latest: dict[str, dict] = {}
    for line in (archive / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            latest[rec["slug"]] = rec
    return sorted(latest.values(), key=lambda r: (-r["year"], r["slug"]))


def card(stats: dict[str, Any]) -> str:
    courts = "\n".join(f"| {k} | {v:,} |" for k, v in stats["by_court"].items())
    return f"""---
license: other
language:
- en
pretty_name: Singapore Supreme Court Judgments
size_categories:
- 10K<n<100K
---

# Singapore Supreme Court Judgments ({stats['first_year']}-{stats['last_year']})

{stats['rows']:,} judgments parsed from [eLitigation](https://www.elitigation.sg/gd), for non-commercial
research. This is an unofficial copy. The official page linked in `source_url` is authoritative.

| Court | Judgments |
|---|---|
{courts}

## Rights and access

The judgments are © Government of Singapore. No licence is granted by this repo. Keep it private:
the source terms bar reproduction for commercial purposes without written permission.

## Changes from the source

- `ids_masked` counts national ID and passport numbers replaced with `{MASK}` ({stats['ids_masked']:,} in {stats['rows_with_ids']:,} judgments). Masking is pattern-based and may miss unusual formats. Names, addresses and other personal details are unchanged.
- Page furniture, counsel lines, footnote markers and signature blocks are removed.
- Some published judgments may since have been corrected or withdrawn. Check `source_url` before relying on one.

## Fields

`paragraphs` holds `{{number, text}}` entries, and `text` joins them. When `paragraphs_numbered` is false
({stats['unnumbered']:,} judgments), the source prints no paragraph numbers, so `number` is only a sequence
index and must not be cited as a pinpoint. {stats['empty']:,} judgments parsed to no text.

Other fields: `slug`, `citation`, `case_name`, `case_number`, `court_code`, `court`, `court_level`, `year`,
`decision_date`, `coram`, `catchwords`, `disposition`, `cites`, `source_url`, `fetched_at`.
"""


def build(out: Path, archive: Path, workers: int | None = None) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    recs = _manifest(archive)
    jobs = [(r, str(archive / str(r["year"]) / f"{r['slug']}.html")) for r in recs]
    workers = workers or max(1, (os.cpu_count() or 2) - 2)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_row_from_paths, jobs, chunksize=50))

    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)
    for old in data.glob("*.parquet"):
        old.unlink()
    n_shards = max(1, -(-len(rows) // SHARD_ROWS))
    for i in range(n_shards):
        table = pa.Table.from_pylist(rows[i * SHARD_ROWS:(i + 1) * SHARD_ROWS])
        pq.write_table(table, data / f"train-{i:05d}-of-{n_shards:05d}.parquet",
                       compression="zstd")

    stats = {
        "rows": len(rows),
        "shards": n_shards,
        "by_court": dict(Counter(r["court_code"] for r in rows).most_common()),
        "first_year": min(r["year"] for r in rows),
        "last_year": max(r["year"] for r in rows),
        "unnumbered": sum(not r["paragraphs_numbered"] for r in rows if r["paragraphs"]),
        "empty": sum(not r["paragraphs"] for r in rows),
        "ids_masked": sum(r["ids_masked"] for r in rows),
        "rows_with_ids": sum(1 for r in rows if r["ids_masked"]),
        "text_chars": sum(len(r["text"]) for r in rows),
    }
    (out / "README.md").write_text(card(stats), encoding="utf-8")
    (out / "export_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def upload(folder: Path, repo: str, api: Any = None, replace: bool = False) -> str:
    """Upload to a private dataset repo; refuse anything that is not private.
    `replace` removes data files absent from `folder` in the same commit (they
    stay in the repo's git history)."""
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi()

    def require_private() -> None:
        if not api.repo_info(repo, repo_type="dataset").private:
            raise PublicRepoError(f"{repo} is not private; nothing further was uploaded")

    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    require_private()  # exist_ok returns an existing repo with its visibility unchanged
    api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=str(folder),
                      allow_patterns=["README.md", "data/*.parquet"],
                      delete_patterns=["data/*"] if replace else None,
                      commit_message=("Replace dataset contents" if replace
                                      else "Add Singapore Supreme Court judgments"))
    require_private()
    return f"https://huggingface.co/datasets/{repo}"


# ---------------------------------------------------------------- page-sized subset

_SENTENCE_END = re.compile(r"[.?!][\"'\u2019\u201d)\]]*$")
_CLAUSE_END = re.compile(r"[;:,][\"'\u2019\u201d)\]]*$")


def catchword_path(catchword: str) -> list[str]:
    """'Tort — Negligence — Duty of care' as comparable parts, whichever dash the
    source used and whatever its casing."""
    return [part.strip().lower().replace("\u2019", "'")
            for part in re.split(r"\s+[\u2014\u2013-]\s+", catchword)]


def matches_category(catchwords: list[str], category: str) -> bool:
    want = catchword_path(category)
    return any(catchword_path(c)[:len(want)] == want for c in catchwords)


def select_judgments(rows: list[dict], category: str, target_words: int,
                     min_words: int) -> list[dict]:
    """Whole judgments in the category until `target_words`: those tagged with it
    first, then the rest, newest first. Numbered judgments only, so every document
    has a real pinpoint. A judgment that would overshoot is skipped, which lets
    a smaller one close the gap."""
    def primary(r: dict) -> bool:
        return matches_category(r["catchwords"][:1], category)

    pool = [r for r in rows if r["paragraphs_numbered"]
            and matches_category(r["catchwords"], category)]
    pool.sort(key=lambda r: (not primary(r), -r["year"], r["slug"]))
    chosen, total = [], 0
    for r in pool:
        words = sum(len(p["text"].split()) for p in r["paragraphs"])
        if words >= min_words and total + words <= target_words:
            chosen.append(r)
            total += words
    return chosen


def allocate_parts(word_counts: list[int], docs: int) -> list[int]:
    """Split `docs` across judgments in proportion to length, summing exactly."""
    mean = sum(word_counts) / docs
    shares = [w / mean for w in word_counts]
    parts = [max(1, int(x)) for x in shares]
    by_remainder = sorted(range(len(shares)), key=lambda i: shares[i] - int(shares[i]),
                          reverse=True)
    for i in by_remainder[:docs - sum(parts)]:
        parts[i] += 1
    return parts


def segment_paragraphs(paragraphs: list[dict], parts: int) -> list[dict]:
    """Cut one judgment into exactly `parts` contiguous pieces of similar length,
    breaking at a paragraph end, else a sentence end, else a clause, near each
    target. No word is dropped, repeated or changed."""
    words, numbers, ends = [], [], []
    for p in paragraphs:
        tokens = p["text"].split()
        words += tokens
        numbers += [p["number"]] * len(tokens)
        ends += [False] * (len(tokens) - 1) + [True] if tokens else []
    size = len(words) / parts
    slack = max(1, int(size * 0.2))

    def strength(i: int) -> int:  # break after word index i
        if ends[i]:
            return 3
        if _SENTENCE_END.search(words[i]):
            return 2
        return 1 if _CLAUSE_END.search(words[i]) else 0

    cuts = [0]
    for k in range(1, parts):
        target = round(k * size)
        lo, hi = max(cuts[-1] + 1, target - slack), min(len(words) - (parts - k), target + slack)
        best = max(range(lo, hi + 1), key=lambda c: (strength(c - 1), -abs(c - target)))
        cuts.append(best)
    cuts.append(len(words))

    out = []
    for a, b in zip(cuts, cuts[1:]):
        pieces, current = [], []
        for i in range(a, b):
            current.append(words[i])
            if ends[i]:
                pieces.append(" ".join(current))
                current = []
        if current:
            pieces.append(" ".join(current))
        out.append({"text": "\n\n".join(pieces), "word_count": b - a,
                    "para_start": numbers[a], "para_end": numbers[b - 1]})
    return out


def subset_card(stats: dict[str, Any]) -> str:
    courts = "\n".join(f"| {k} | {v:,} |" for k, v in stats["by_court"].items())
    return f"""---
license: other
language:
- en
pretty_name: Singapore Negligence Judgments (Page-Sized Passages)
size_categories:
- 1K<n<10K
---

# Singapore Negligence Judgments: Page-Sized Passages

{stats['docs']:,} passages of about {stats['words_per_doc']} words each, {stats['words']:,} words in total, cut from
{stats['judgments']} Singapore Supreme Court judgments catalogued under `{stats['category']}`, decided
{stats['first_year']}-{stats['last_year']}. It is for retrieval over how Singapore courts decide negligence claims.

One passage is roughly one page: modern judgment PDFs carry about {stats['words_per_doc']} words a page.

This is an unofficial copy from [eLitigation](https://www.elitigation.sg/gd). The official page in `source_url` is
authoritative. A catchword tag means negligence was in issue, not that it is the only subject of the judgment.

| Court | Judgments |
|---|---|
{courts}

## Rights and access

The judgments are © Government of Singapore. No licence is granted by this repo. Keep it private:
the source terms bar reproduction for commercial purposes without written permission.

## Changes from the source

- National ID and passport numbers are replaced with `{MASK}`. Masking is pattern-based and may miss unusual formats. Names, addresses and other personal details are unchanged.
- Page furniture, counsel lines, footnote markers and signature blocks are removed.
- Section headings carried into a paragraph appear in square brackets. Paragraph numbers are not in `text`; use `para_start` and `para_end`.
- Some published judgments may since have been corrected or withdrawn. Check `source_url` before relying on one.

## Fields

`doc_id`, `part`, `parts_total`, `text`, `word_count`, `para_start`, `para_end`, `citation`, `case_name`,
`court_code`, `court`, `year`, `decision_date`, `coram`, `catchwords`, `source_url`.
"""


def build_subset(source: Path, out: Path, category: str, docs: int,
                 words_per_doc: int) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows: list[dict] = []
    for f in sorted((source / "data").glob("*.parquet")):
        rows += pq.read_table(f).to_pylist()
    chosen = select_judgments(rows, category, docs * words_per_doc, words_per_doc)
    counts = [sum(len(p["text"].split()) for p in r["paragraphs"]) for r in chosen]
    if sum(counts) < 0.99 * docs * words_per_doc:
        raise ValueError(f"{category!r} holds only {sum(counts):,} usable words")
    parts = allocate_parts(counts, docs)

    records = []
    for r, n in zip(chosen, parts):
        for i, seg in enumerate(segment_paragraphs(r["paragraphs"], n), start=1):
            records.append({
                "doc_id": f"{r['slug']}-{i:04d}", "part": i, "parts_total": n, **seg,
                "citation": r["citation"], "case_name": r["case_name"],
                "court_code": r["court_code"], "court": r["court"], "year": r["year"],
                "decision_date": r["decision_date"], "coram": r["coram"],
                "catchwords": r["catchwords"], "source_url": r["source_url"],
            })

    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)
    for old in data.glob("*.parquet"):
        old.unlink()
    pq.write_table(pa.Table.from_pylist(records), data / "train-00000-of-00001.parquet",
                   compression="zstd")
    stats = {
        "category": category, "docs": len(records), "words_per_doc": words_per_doc,
        "words": sum(r["word_count"] for r in records), "judgments": len(chosen),
        "by_court": dict(Counter(r["court_code"] for r in chosen).most_common()),
        "first_year": min(r["year"] for r in chosen),
        "last_year": max(r["year"] for r in chosen),
        "shortest_doc": min(r["word_count"] for r in records),
        "longest_doc": max(r["word_count"] for r in records),
    }
    (out / "README.md").write_text(subset_card(stats), encoding="utf-8")
    (out / "export_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    settings = get_settings()
    default_out = settings.data_dir / "export" / "sg-judgments"
    p = argparse.ArgumentParser(description="Private Hugging Face export of the judgments")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="parse the archive into Parquet (no network)")
    b.add_argument("--out", type=Path, default=default_out)
    c = sub.add_parser("subset", help="cut one category into page-sized documents")
    c.add_argument("--category", default="Tort \u2014 Negligence")
    c.add_argument("--docs", type=int, default=10_000)
    c.add_argument("--words-per-doc", type=int, default=300)
    c.add_argument("--source", type=Path, default=default_out)
    c.add_argument("--out", type=Path, default=settings.data_dir / "export" / "sg-negligence")
    u = sub.add_parser("upload", help="upload the export to a private dataset repo")
    u.add_argument("--repo", required=True, help="<user-or-org>/<dataset-name>")
    u.add_argument("--folder", type=Path, default=default_out)
    u.add_argument("--replace", action="store_true", help="remove data files not in --folder")
    args = p.parse_args()
    if args.command == "build":
        print(json.dumps(build(args.out, settings.data_dir / "raw" / "elitigation"), indent=2))
    elif args.command == "subset":
        print(json.dumps(build_subset(args.source, args.out, args.category, args.docs,
                                      args.words_per_doc), indent=2))
    else:
        print("uploaded privately:", upload(args.folder, args.repo, replace=args.replace))


if __name__ == "__main__":
    main()

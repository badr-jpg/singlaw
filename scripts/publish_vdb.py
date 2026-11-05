"""Package the built index and upload it to a private Hugging Face dataset.

    cd backend
    python ../scripts/publish_vdb.py build --repo <user>/<name>   # data/export/vdb; no network
    python ../scripts/publish_vdb.py upload --repo <user>/<name>

`build` needs pyarrow and a passing scripts/verify_vdb.py report. The package holds
what the app reads (qdrant/, db/, cache/, laid out like data/) plus a Parquet copy
of every point, a manifest and a dataset card. Uploading goes through
app.hf_export.upload, which only ever writes to a private repo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.hf_export import upload  # noqa: E402

SHARD_ROWS = 5000
STATUTES = {"repo": "Kaidon-Ng/singapore-statutes", "revision": "8b81a0ca8c6d7eededec8637cb2efdb58359650c"}
JUDGMENTS = {"repo": "badlaldh/singapore-judgments", "revision": "290e9687e09032a690d22089509ed047627c629e"}
EMBEDDER_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
# tables that would hold a person's own activity; must be empty in anything published
PRIVATE_TABLES = ("conversations", "messages", "user_documents", "businesses",
                  "message_feedback", "billing_waitlist")
ALLOW = ["README.md", "manifest.json", "verification.json", "data/*.parquet",
         "qdrant/**", "db/app.sqlite3", "cache/bm25_stats.json"]


def export_parquet(qdrant_path: Path, out: Path) -> list[dict]:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from qdrant_client import QdrantClient

    client = QdrantClient(path=str(qdrant_path))
    rows, offset = [], None
    while True:
        batch, offset = client.scroll("sg_law", limit=1000, offset=offset,
                                      with_payload=True, with_vectors=True)
        for p in batch:
            pl = p.payload
            rows.append({
                "point_id": str(p.id), "chunk_id": pl["chunk_id"], "doc_id": pl["doc_id"],
                "source_dataset": JUDGMENTS["repo"] if pl["doc_type"] == "judgment" else STATUTES["repo"],
                "doc_type": pl["doc_type"], "citation": pl["citation"], "title": pl["title"],
                "authority_tier": pl["authority_tier"], "status": pl["status"],
                "treatment": pl["treatment"], "court": pl["court"], "court_level": pl["court_level"],
                "decision_date": pl["decision_date"], "sso_version_date": pl["sso_version_date"],
                "hierarchy_path": pl["hierarchy_path"], "cites": pl["cites"],
                "source_url": pl["source_url"], "context": pl["context"], "text": pl["text"],
                "dense": p.vector["dense"], "sparse_indices": p.vector["sparse"].indices,
                "sparse_values": p.vector["sparse"].values,
            })
        if offset is None:
            break
    client.close()
    rows.sort(key=lambda r: (r["doc_type"], r["doc_id"], r["chunk_id"]))

    schema = pa.schema([
        ("point_id", pa.string()), ("chunk_id", pa.string()), ("doc_id", pa.string()),
        ("source_dataset", pa.string()), ("doc_type", pa.string()), ("citation", pa.string()),
        ("title", pa.string()), ("authority_tier", pa.int8()), ("status", pa.string()),
        ("treatment", pa.string()), ("court", pa.string()), ("court_level", pa.int8()),
        ("decision_date", pa.string()), ("sso_version_date", pa.string()),
        ("hierarchy_path", pa.list_(pa.string())), ("cites", pa.list_(pa.string())),
        ("source_url", pa.string()), ("context", pa.string()), ("text", pa.string()),
        ("dense", pa.list_(pa.float32(), 1024)), ("sparse_indices", pa.list_(pa.uint32())),
        ("sparse_values", pa.list_(pa.float32())),
    ])
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)
    for old in data.glob("*.parquet"):
        old.unlink()
    n = max(1, -(-len(rows) // SHARD_ROWS))
    for i in range(n):
        table = pa.Table.from_pylist(rows[i * SHARD_ROWS:(i + 1) * SHARD_ROWS], schema=schema)
        pq.write_table(table, data / f"sg_law-{i:05d}-of-{n:05d}.parquet", compression="zstd")
    return rows


def card(m: dict, repo: str) -> str:
    c, d = m["chunks"], m["documents"]
    t = ", ".join(f"{v} {k}" for k, v in sorted(m["judgment_treatment"].items(), key=lambda kv: -kv[1]))
    edges = " and ".join(f"{v:,} {k}" for k, v in sorted(m["citation_edges"].items()))
    p = m["probes"]
    return f"""---
license: other
license_name: mixed-singapore-government-copyright
language:
- en
pretty_name: "SingLaw Vector Index: 512 Singapore Acts and Negligence Judgment Passages"
size_categories:
- 10K<n<100K
task_categories:
- text-retrieval
- question-answering
tags:
- legal
- singapore
- vector-database
- qdrant
- embeddings
- hybrid-search
- rag
configs:
- config_name: sg_law
  default: true
  data_files:
  - split: train
    path: data/*.parquet
---

# SingLaw Vector Index

The retrieval index for [SingLaw](https://github.com/badr-jpg/singlaw), a Singapore legal-information assistant:
{m['total_chunks']:,} chunks with dense and sparse vectors, as an embedded Qdrant database and as Parquet.

**This is a research index, not legal advice and not an authoritative text of Singapore law.**

## Contents

| Source | Type (`doc_type`) | Documents | Chunks |
|---|---|---:|---:|
| [{STATUTES['repo']}](https://huggingface.co/datasets/{STATUTES['repo']}) @ `{STATUTES['revision'][:7]}` | Acts (`act`) | {d['act']:,} | {c['act']:,} |
| [{JUDGMENTS['repo']}](https://huggingface.co/datasets/{JUDGMENTS['repo']}) @ `{JUDGMENTS['revision'][:7]}` | Judgments (`judgment`) | {d['judgment']:,} | {c['judgment']:,} |

**The judgments are a narrow subset.** The 10,000 judgment chunks are about 300-word passages from {d['judgment']} Supreme Court
judgments catalogued under *Tort — Negligence* (2001-2026). They are not 10,000 separate judgments, and other areas of case law are not covered.

**The legislation is Acts only, and six Acts are missing.** The source's 1,782 pieces of subsidiary legislation are not indexed. Of the 535
documents it labels as Acts, 17 are really Regulations, Orders or Notifications and are correctly left out. The pipeline also leaves out 6 that should be in:

- The Judicial Proceedings (Regulation of Reports) Act 1960, Miscellaneous Offences (Public Order and Nuisance) Act 1906, Public Order Act 2009, Public Order and Safety (Special Powers) Act 2018, and Regulation of Imports and Exports Act 1995. A name filter treats "Order" and "Regulation" in their titles as signs of subsidiary legislation.
- The Independence of Singapore Agreement 1965. Its whole text is one row, which the pipeline treats as a cover page.

Questions on these will not find them here.

## Files

| Path | What it is |
|---|---|
| `qdrant/` | Embedded Qdrant database (collections `sg_law`, and an empty `user_docs`) |
| `db/app.sqlite3` | SingLaw's corpus registry and citation graph; conversation and upload tables are empty |
| `cache/bm25_stats.json` | Corpus statistics for encoding sparse vectors |
| `data/*.parquet` | The same {m['total_chunks']:,} points, with vectors, in {m['parquet_shards']} shards |
| `manifest.json` | Build details: models, revisions, counts |
| `verification.json` | Results of the checks run before publishing |

## Use it

With the SingLaw repo, download into its `data/` folder and run the app:

```bash
hf download {repo} --repo-type dataset --include "qdrant/*" --include "db/*" --include "cache/*" --local-dir data
```

Or query the database directly (one process at a time):

```python
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("{m['embedding']['model']}", trust_remote_code=True)
client = QdrantClient(path="qdrant")
query = model.encode("notice period for ending an employment contract",
                     prompt_name="query", normalize_embeddings=True)
hits = client.query_points("sg_law", query=query.tolist(), using="dense", limit=5).points
print([h.payload["citation"] for h in hits])
```

Or read the Parquet copy without Qdrant: `load_dataset("{repo}", split="train")`.

## Vectors

- **`dense`**: `{m['embedding']['model']}` @ `{EMBEDDER_REVISION[:7]}`, {m['embedding']['dim']} dimensions, cosine distance. The model runs in bfloat16 and normalises at that precision, so norms are within 2⁻⁸ of 1 ({m['dense_norm_range'][0]:.4f} to {m['dense_norm_range'][1]:.4f}). Renormalise before using a raw dot product. Documents are embedded as `context` + two newlines + `text`. Queries must use the model's `query` prompt.
- **`sparse`**: BM25 term weights over bm25s tokens (English stopwords removed) with blake2b 32-bit token hashes. Qdrant applies IDF at query time. Query vectors use the same tokeniser and hash, with every weight 1.0. Document length normalisation used the running average at encoding time, so weights depend slightly on indexing order (Acts first, then judgments).

## Fields

| Field | Meaning |
|---|---|
| `chunk_id`, `doc_id`, `point_id` | Deterministic ids. `point_id` is the uuid5 of `chunk_id` |
| `source_dataset` | Parquet only: the source Hugging Face dataset |
| `doc_type` | `act` or `judgment` |
| `citation` | e.g. `Employment Act 1968, s 10`, or `[2026] SGCA 33 at [1]–[3]` |
| `title`, `hierarchy_path` | Document name, and its path down to the section or passage |
| `authority_tier` | 1 Constitution, 2 Act, 4 binding judgment, 5 lower court |
| `status`, `sso_version_date` | Legislation: all `in_force` (the source excludes repealed law) and the consolidation date |
| `court`, `court_level`, `decision_date` | Judgments only |
| `treatment`, `cites` | Judgments only. See the limits below |
| `source_url` | The eLitigation page for judgments; SSO's home page for Acts |
| `context`, `text` | Generated context sentence, and the source text |

## Known limits

- **Acts link to SSO's home page**, not the provision: the source has no deep links. Check SSO for the latest version.
- **Passage citations are ranges.** A passage can start or end inside a paragraph, and passages of one long paragraph share a citation (`chunk_id` still differs). Citation edges carry no paragraph number.
- **`treatment` is not a statement of current authority.** It is inferred only from explicit language in these {d['judgment']} judgments (results: {t}). Cases overruled elsewhere are not detected, so `unknown` or `good` does not mean a case is still good law.
- **The citation graph is partial.** It matches neutral citations such as `[2018] SGCA 1` and statute references, not law-report citations such as `[2019] 2 SLR 341` ({edges} edges).
- **Judgments may be corrected or withdrawn after publication.** Check `source_url` before relying on one.
- **In the SingLaw app without an LLM key, exact section lookup needs the form `s 10 of the Employment Act 1968`.** The bare form `Employment Act 1968, s 10` falls back to ordinary search and may not rank that section first. This is query parsing, not the index.

## Checks

All structural checks passed before publishing: counts, ids, vector shape and norms, and each of {m['self_retrieval']['sample']} sampled chunks retrieving itself. {p['ok']} of {p['total']} relevance probes through the full retrieval pipeline matched, and the miss is the query form described above. The probes are a spot check, not an evaluation of retrieval quality. Details are in `verification.json`.

## Rights and access

Keep this repo private. No licence is granted by it.

- **Judgments** are © Government of Singapore. The source terms bar reproduction for commercial purposes without written permission. National ID and passport numbers were masked by the source dataset using patterns that may miss unusual formats. Names, addresses and other personal details are unchanged.
- **Legislation** is © Singapore Government, reproduced under clause 13 of the Singapore Statutes Online Terms of Use. Check https://sso.agc.gov.sg for the latest version. Material downloaded from SSO is not an authoritative text: section 48 of the Interpretation Act 1965 does not apply to it, and the Gazette remains the authoritative text.

## Build

Built {m['built_at'][:10]} on {m['build']['gpu']} (torch {m['build']['torch']}, qdrant-client {m['build']['qdrant_client']}) from
`badr-jpg/singlaw` at `{m['build']['repo_commit'][:7]}`{' plus local changes not yet committed: Windows fixes and the judgment passage loader' if m['build']['repo_dirty'] else ''}.
"""


def build(settings, repo: str) -> None:
    import torch
    from importlib.metadata import version

    out = settings.data_dir / "export" / "vdb"
    report = out / "verification.json"
    if not report.exists():
        sys.exit("run scripts/verify_vdb.py first")
    v = json.loads(report.read_text(encoding="utf-8"))
    if v["structural_failures"]:
        sys.exit(f"verification failed: {v['structural_failures']}")

    # database first: stop before copying anything if it holds a person's activity
    con = sqlite3.connect(settings.db_path)
    for table in PRIVATE_TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if n:
            sys.exit(f"{table} holds {n} rows; refusing to package a used database")
    (out / "db").mkdir(parents=True, exist_ok=True)
    db_copy = out / "db" / "app.sqlite3"
    db_copy.unlink(missing_ok=True)
    con.execute("VACUUM INTO ?", (str(db_copy),))
    con.close()

    shutil.rmtree(out / "qdrant", ignore_errors=True)
    shutil.copytree(settings.qdrant_path, out / "qdrant", ignore=shutil.ignore_patterns(".lock"))
    (out / "cache").mkdir(exist_ok=True)
    shutil.copy2(settings.cache_dir / "bm25_stats.json", out / "cache" / "bm25_stats.json")

    rows = export_parquet(settings.qdrant_path, out)
    git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
    chunks = Counter(r["doc_type"] for r in rows)
    manifest = {
        "name": "SingLaw vector index",
        "built_at": datetime.now(UTC).isoformat(),
        "total_chunks": len(rows),
        "chunks": dict(chunks),
        "documents": v["documents"],
        "parquet_shards": len(list((out / "data").glob("*.parquet"))),
        "judgment_treatment": v["judgment_treatment"],
        "citation_edges": v["citation_edges"],
        "dense_norm_range": v["dense_norm_range"],
        "self_retrieval": v["self_retrieval"],
        "probes": {"ok": v["probes_ok"], "total": v["probes_total"]},
        "sources": {"act": STATUTES, "judgment": JUDGMENTS},
        "embedding": {"model": settings.embedding_model_resolved, "revision": EMBEDDER_REVISION,
                      "dim": 1024, "distance": "cosine", "normalized": True,
                      "document_text": "context + \\n\\n + text", "query_prompt": "query"},
        "sparse": {"scheme": "bm25-tf", "k1": 1.5, "b": 0.75, "tokenizer": "bm25s, english stopwords",
                   "hash": "blake2b 32-bit little-endian", "qdrant_modifier": "idf"},
        "qdrant": {"mode": "embedded", "collections": ["sg_law", "user_docs"]},
        "build": {"gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
                  "torch": torch.__version__, "qdrant_client": version("qdrant-client"),
                  "repo": "https://github.com/badr-jpg/singlaw",
                  "repo_commit": git("rev-parse", "HEAD"), "repo_dirty": bool(git("status", "--porcelain"))},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(card(manifest, repo), encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"packaged {len(rows):,} points into {out} ({size / 2**30:.2f} GiB)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo", required=True, help="<user-or-org>/<dataset-name>, named in the card")
    u = sub.add_parser("upload")
    u.add_argument("--repo", required=True, help="<user-or-org>/<dataset-name>")
    args = p.parse_args()
    settings = get_settings()
    if args.command == "build":
        build(settings, args.repo)
    else:
        url = upload(settings.data_dir / "export" / "vdb", args.repo, allow_patterns=ALLOW,
                     commit_message="Add SingLaw vector index (Qdrant + Parquet)")
        print("uploaded privately:", url)


if __name__ == "__main__":
    main()

# Corpus and index

Data and source documents never go in this repo; they belong on Hugging Face or in the ignored
local `data/` folders. Git holds only code, docs and the manifest.

The corpus has two sources, each loaded by its own command.

| Content | Local path | Source | Terms |
|---|---|---|---|
| Judgments: 10,003 Supreme Court decisions, 2000–2026, with case names and dates (9,994 parse, giving 155,138 chunks) | `data/raw/elitigation/` (not in git) | [eLitigation](https://www.elitigation.sg), via `python -m app.elitigation fetch` | Judiciary terms: fair dealing for private study, research, criticism or review; no commercial reproduction without written permission |
| Legislation: 512 Acts (33,160 chunks). The dataset labels 535 documents as Acts, 22 of which are really Regulations or Notifications. About 1,800 pieces of subsidiary legislation are available but not indexed (`doc_types` in the manifest). | `data/corpus/sso_statutes/` (not in git) | Hugging Face copy of SSO, [Kaidon-Ng/singapore-statutes](https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes) ("LawBot Project", 2026) | SSO Terms of Use clause 13: subject to Singapore Government copyright; check SSO for the latest version |

`data/corpus/manifest.json` lists the legislation files and how to chunk them.

SSO blocked automated crawling (HTTP 403 at 05:00 on 5 Nov), so no pages have been crawled; the
legislation comes from the published copy above.

## Get the legislation files

```bash
mkdir -p data/corpus/sso_statutes
curl -L -o data/corpus/sso_statutes/sections.parquet  https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes/resolve/main/data/sections.parquet
curl -L -o data/corpus/sso_statutes/documents.parquet https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes/resolve/main/data/documents.parquet
cd backend && uv run --with pandas --with pyarrow python ../scripts/prepare_sso_statutes.py
```

Without these files the seed step stops with an error before indexing anything. The chunk export
below only prints a warning and leaves the Acts out.

Citations for these Acts link to SSO's home page, not the provision, because the dataset has no
SSO URLs or Act codes. Where two documents share a truncated name, the later ones get `-2`, `-3`
on their ids, with Acts numbered first, but their citations still show the shared name.

## Export the chunks (no index needed)

```bash
cd backend
uv run --with matplotlib python ../scripts/corpus_report.py --from-corpus ../data/corpus
```

This writes `data/export/chunks.jsonl` (not in git), with one JSON object per chunk: `chunk_id`,
`doc_id`, `citation`, `title`, `doc_type`, `status`, `authority_tier`, `court`, `decision_date`,
`source_url`, `context`, `text`. It includes the judgments if `data/raw/elitigation` exists.

**Use `chunk_id` as the gold-passage id in the eval set.** Ids are deterministic, so they match the
index whichever embedding model is used. Eval labels made from the earlier MLEB judgment export do
not carry over: those judgments are no longer in the corpus.

## Build the index

Stop the server first: embedded Qdrant allows one process at a time.

```bash
cd backend
uv run python -m app.crawler seed --archive ../data/corpus   # Acts
uv run python -m app.elitigation index                       # judgments; already-indexed ones are skipped
```

Both are additive, so they can extend an existing index. `make clean` deletes the index and the
database, and switching `MODEL_PROFILE` requires it because the vector size changes.

Measured speeds: `full` profile about 0.4 chunks/s on a MacBook Air (about 23 h for the 33,160 Act
chunks; use the fastest machine available); judgments about 16 per minute with the current
profile (about 10.5 h for the full archive).

## Rules

- Never crawl SSO outside 05:00–07:00 SGT (`python -m app.crawler crawl-full` refuses).
- `data/archive/` holds dev fixtures only; the tests use them.

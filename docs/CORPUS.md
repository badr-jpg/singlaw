# Corpus and index

Data and source documents never go in this repo; they belong on Hugging Face or in the ignored
local `data/` folders. Git holds only code, docs and the manifest.

The corpus has two sources, both listed in `data/corpus/manifest.json` and loaded by one seed command.

| Content | Local path | Source | Terms |
|---|---|---|---|
| Judgments: 10,000 passages (about 300 words each) from 214 Supreme Court judgments on Tort — Negligence, 2001–2026, with case names and dates | `data/corpus/elitigation_hf/` (not in git) | eLitigation, via the group's Hugging Face dataset [badlaldh/singapore-judgments](https://huggingface.co/datasets/badlaldh/singapore-judgments) (`judgments` subset) | Judiciary terms: fair dealing for private study, research, criticism or review; no commercial reproduction without written permission. © Government of Singapore: keep the dataset and downloads private |
| Legislation: 512 Acts (33,160 chunks). The dataset labels 535 documents as Acts, 22 of which are really Regulations or Notifications. About 1,800 pieces of subsidiary legislation are available but not indexed (`doc_types` in the manifest). | `data/corpus/sso_statutes/` (not in git) | Hugging Face copy of SSO, [Kaidon-Ng/singapore-statutes](https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes) ("LawBot Project", 2026) | SSO Terms of Use clause 13: subject to Singapore Government copyright; check SSO for the latest version |

`data/corpus/manifest.json` lists both sources and how to chunk them.

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

## Get the judgments

```bash
cd backend
uv run --with huggingface_hub hf download badlaldh/singapore-judgments --repo-type dataset --local-dir ../data/corpus/elitigation_hf
uv run --with pyarrow python -m app.ingest.hf_elitigation status
```

`status` should report 10,000 passages from 214 judgments. Each passage is one chunk, with id
`<citation-and-case-name slug>:part<n>`, cited by the paragraphs it covers ("[2019] SGCA 12 at
[14]–[19]"). The dataset's work/family legislation subsets are skipped; legislation comes from the
SSO copy. If the dataset is made private, log in first with `uv run --with huggingface_hub hf auth login`.

The raw-archive route (`python -m app.elitigation fetch` / `index`) is not part of the final corpus:
it chunks the judgments differently, so its chunk ids would not match the eval labels.

## Export the chunks (no index needed)

```bash
cd backend
uv run --with matplotlib --with pyarrow python ../scripts/corpus_report.py --from-corpus ../data/corpus
```

This writes `data/export/chunks.jsonl` (not in git), with one JSON object per chunk: `chunk_id`,
`doc_id`, `citation`, `title`, `doc_type`, `status`, `authority_tier`, `court`, `decision_date`,
`source_url`, `context`, `text`. Expected: about 726 documents and 43,160 chunks (10,000 judgment passages + 33,160 Act chunks).

**Use `chunk_id` as the gold-passage id in the eval set.** Ids are deterministic, so they match the
index whichever embedding model is used. Eval labels made from the earlier MLEB judgment export do
not carry over: those judgments are no longer in the corpus.

## Build the index

Stop the server first: embedded Qdrant allows one process at a time.

```bash
cd backend
uv run --with pyarrow python -m app.crawler seed --archive ../data/corpus   # judgments + Acts
```

Seeding is additive (chunk ids are fixed), so re-running it updates rather than duplicates. `make clean` deletes the index and the
database, and switching `MODEL_PROFILE` requires it because the vector size changes.

Measured speeds: `full` profile about 0.4 chunks/s on a MacBook Air (about 23 h for the 33,160 Act
chunks; use the fastest machine available); judgments about 16 per minute with the current
profile (about 10.5 h for the full archive).

## Rules

- Never crawl SSO outside 05:00–07:00 SGT (`python -m app.crawler crawl-full` refuses).
- `data/archive/` holds dev fixtures only; the tests use them.

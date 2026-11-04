# Corpus and index (Subgroup A)

## What is in `data/corpus/`

| Path | Source | Licence |
|---|---|---|
| `hf/corpus.jsonl` | 500 Singapore judgments (118 Court of Appeal, 382 High Court, 2000–2025) from the MLEB dataset [isaacus/singaporean-judicial-keywords](https://huggingface.co/datasets/isaacus/singaporean-judicial-keywords) | CC BY 4.0 — cite Butler, Butler & Malec (2025), *The Massive Legal Embedding Benchmark (MLEB)*, arXiv:2510.19365 |
| `sso_statutes/sections.jsonl` | 512 Acts indexed (33,160 chunks; the dataset labels 535 rows as Acts, 22 of which are really Regulations or Notifications) + ~1,800 subsidiary legislation, from the Hugging Face copy of SSO [Kaidon-Ng/singapore-statutes](https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes) ("LawBot Project", 2026). Acts only are indexed (`doc_types` in the manifest). | SSO Terms of Use clause 13: subject to Singapore Government copyright; check SSO for the latest version |
| `manifest.json` | Lists every file and how to chunk it | — |

Total: 1,012 documents · 45,321 chunks · ~12.0 million words · 53,839 types (512 Acts: 33,160 chunks; 500 judgments: 12,161 chunks).

SSO blocked automated crawling (HTTP 403 at 05:00 on 5 Nov), so no pages were crawled; the
legislation comes from the published copy above instead.

### Get the legislation files (not in git: too large for the web uploader)

```bash
mkdir -p data/corpus/sso_statutes
curl -L -o data/corpus/sso_statutes/sections.parquet  https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes/resolve/main/data/sections.parquet
curl -L -o data/corpus/sso_statutes/documents.parquet https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes/resolve/main/data/documents.parquet
cd backend && uv run --with pandas --with pyarrow python ../scripts/prepare_sso_statutes.py
```

## Subgroup C — get the chunks (no index needed, ~10 s)

`data/export/chunks.jsonl` is committed. To regenerate it:

```bash
cd backend
uv run --with matplotlib python ../scripts/corpus_report.py --from-corpus ../data/corpus
```

One JSON object per chunk: `chunk_id`, `doc_id`, `citation`, `title`, `doc_type`, `status`,
`authority_tier`, `court`, `decision_date`, `source_url`, `context`, `text`.
**Use `chunk_id` as the gold-passage id in the eval set.** Ids are deterministic
(`<doc_id>:para<lo>-<hi>`, `:part<n>`, or `<id>.<k>` for split oversized chunks), so they match
the index whichever embedding model is used.

## Subgroup B — build the index

```bash
cd "<repo>" && make clean
cd backend
MODEL_PROFILE=dev  uv run python -m app.crawler seed --archive ../data/corpus   # MiniLM, minutes
MODEL_PROFILE=full uv run python -m app.crawler seed --archive ../data/corpus   # Qwen3-0.6B, final
```

Measured on a MacBook Air: the `full` profile embeds about 0.4 chunks/s (≈ 8 h for 12,161
chunks), so build `full` on the fastest machine available (Apple M-Pro/Max or an NVIDIA GPU).
Switching profile needs `make clean` first (vector size changes). Stop `make dev` before
seeding: embedded Qdrant allows one process at a time.

## Rules

- **Freeze: Thu 5 Nov 12:00.** No parser, chunking or corpus changes after it.
- The dev fixture set in `data/archive/` is not used any more.
- Never crawl SSO outside 05:00–07:00 SGT (`python -m app.crawler crawl-full` refuses).

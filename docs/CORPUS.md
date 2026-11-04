# Corpus and index (Subgroup A)

## What is in `data/corpus/`

| Path | Source | Licence |
|---|---|---|
| `hf/corpus.jsonl` | 500 Singapore judgments (118 Court of Appeal, 382 High Court, 2000–2025) from the MLEB dataset [isaacus/singaporean-judicial-keywords](https://huggingface.co/datasets/isaacus/singaporean-judicial-keywords) | CC BY 4.0 — cite Butler, Butler & Malec (2025), *The Massive Legal Embedding Benchmark (MLEB)*, arXiv:2510.19365 |
| `acts/*.html.gz` | Acts from Singapore Statutes Online, crawled 05:00–07:00 SGT only (added Thu 5 Nov if the crawl succeeds) | © Singapore Government, SSO terms of use |
| `manifest.json` | Lists every file and how to chunk it | — |

Current size: 500 documents · 12,161 chunks · 3,437,863 words · 38,809 types (meets the brief's 10,000 / 100,000).

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

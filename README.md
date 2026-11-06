# SingLaw

A Singapore legal-information assistant. Ask a question in plain English — about your lease, your employment contract, the business you run — and get an answer built only from the actual Acts, regulations and judgments, with a citation on every sentence that you can open and read.

Accuracy-first by design: answers state the date they are current to, repealed and overruled law is flagged rather than silently served, and a grounding check marks any sentence that could not be matched to a source. **This is legal information, not legal advice.**

## What it does

- **Cited answers, streamed** — every claim carries a `[citation]` chip that opens the provision or judgment paragraph it came from, with its hierarchy, status and official link.
- **Current-law aware** — hard filters exclude repealed/spent law unless you ask about the past; a citation graph marks overruled and distinguished judgments; authority-tier ranking puts a binding Court of Appeal decision above a guidance note.
- **Your documents, in context** — upload a contract or letter and ask about it; business workspaces keep a company's profile and documents together.
- **Explore the corpus** — browse Acts → Parts → Sections, search the law directly, see version history and citing judgments.
- **Honest UI** — low-confidence framing, high-stakes referrals (criminal, immigration, deadlines, eviction), a retrieval inspector showing exactly why each source was ranked and where the time went.

## Knowledge base

SingLaw's knowledge base comes from two Hugging Face datasets:

| Content | Source |
|---|---|
| 512 Singapore Acts | [`Kaidon-Ng/singapore-statutes`](https://huggingface.co/datasets/Kaidon-Ng/singapore-statutes) |
| 10,000 passages from 214 Supreme Court negligence judgments | [`badlaldh/singapore-judgments`](https://huggingface.co/datasets/badlaldh/singapore-judgments) |

See [docs/CORPUS.md](docs/CORPUS.md) for how the index is built and what it doesn't cover.

## Technology stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12 · FastAPI (async) · SSE streaming |
| Retrieval | Hybrid dense + BM25 sparse → RRF → cross-encoder rerank → authority-aware blend |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B`, local, in-process (`sentence-transformers`) |
| Reranker | `Qwen/Qwen3-Reranker-0.6B`, local |
| Vector store | Qdrant **embedded** (on-disk, no server/Docker), two collections: `sg_law`, `user_docs` |
| Relational store | SQLite (WAL) — conversations, documents, citation graph, crawl state, caches |
| LLM | MiniMax (`MiniMax-M3` for answers, `MiniMax-M3.1-Flash` for helper calls) via an OpenAI-compatible provider interface — generation, query analysis, rewriting/HyDE only; swap to local vLLM by changing one URL |
| Ingestion | Window-guarded SSO crawler (05:00–07:00 SGT, per SSO terms), structure-aware legislation/judgment parsers, section-level chunking with derived context |
| Frontend | React 19 · TypeScript · Vite · TanStack Router/Query · shadcn/ui · Tailwind v4 · streamdown |
| Billing | Plan catalogue in code; Stripe Checkout optional (waitlist fallback) |
| Tests | 139 backend (pytest, offline stub models) · 44 frontend (vitest) |

Everything except the LLM call runs on your machine.

## Run it

Requires [uv](https://docs.astral.sh/uv/) (Python ≥ 3.11) and Node ≥ 20. Nothing needs compiling beyond the frontend build below.

1. **Install the dependencies.** Exact versions are pinned in `backend/uv.lock` and `frontend/package-lock.json`.

   ```bash
   make setup
   make build
   ```

2. **Put the knowledge base in place.** Unzip the data archive, then copy its `index/` folders into `data/` so you have `data/qdrant`, `data/db` and `data/cache`. Team members with access to the private dataset can run `HF_TOKEN=... make index` instead.

3. **Add an LLM key.** Copy `.env.example` to `.env` and set `MINIMAX_API_KEY`. Without a key, retrieval still works and answers fall back to a cited extractive listing.

4. **Start the app.** The first run downloads the embedding and reranker models (about 2.2 GB) from Hugging Face.

   ```bash
   FUSION_TOP=50 RERANKER_MODEL=Qwen/Qwen3-Reranker-0.6B make dev
   ```

   Open http://localhost:8000. `FUSION_TOP=50` is the rerank depth used in the evaluation; the code default is 150, which is slower.

Embedded Qdrant allows one process at a time, so stop the server before running anything else that opens the index.

To try the app without the full index, use small models and the bundled test data instead: `MODEL_PROFILE=dev make seed && MODEL_PROFILE=dev make dev`.

To rebuild the index from source, see [docs/CORPUS.md](docs/CORPUS.md).

Routes: `/` chat · `/sources` corpus explorer · `/welcome` landing · `/billing` plans · `/terms`.

## Reproduce the evaluation

See [eval/README.md](eval/README.md).

## Development

```bash
make test            # backend tests (offline)
cd frontend && npm test
make frontend-dev    # Vite on :5173 with /api proxied to :8000
make eval            # retrieval + grounding evaluation (stop the server first — embedded Qdrant is single-process)
make sync            # incremental SSO sync; only runs inside the 05:00–07:00 SGT window
```

## Repository layout

```
backend/app/           FastAPI app: config, retrieval, answer (grounded SSE), crawler, billing, api/
backend/app/ingest/    parsers, chunker + structural context, citation graph, ingest pipeline
backend/tests/         pytest suite + fixtures
frontend/src/          SingLaw SPA: routes/, components/singlaw/, lib/api.ts, lib/chat-stream.ts
eval/                  50-question evaluation set + runner
data/archive/          bundled dev seed corpus      data/content/  suggestions & discoveries
docs/ARCHITECTURE.md   full technical reference     DECISIONS.md   decision log
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the full technical reference: scraping, parsing, chunking, embeddings and model selection, the nine-stage retrieval pipeline, citation graph, answer generation and the safety layer, storage, API reference, evaluation, every configuration variable.
- [DECISIONS.md](DECISIONS.md) — why things are the way they are.
- [docs/superpowers/plans/2026-08-11-sg-law-rag.md](docs/superpowers/plans/2026-08-11-sg-law-rag.md) — original spec and the frozen API contract (v1 + v2 addendum).

## Legal notices

Legislation is © Singapore Government, reproduced with the permission of the Attorney-General's Chambers under the Singapore Statutes Online terms of use. Material downloaded from SSO is not an authoritative text (s 48 Interpretation Act 1965 does not apply); the Gazette is. SingLaw provides legal information, not legal advice, and does not draft documents for filing in court.

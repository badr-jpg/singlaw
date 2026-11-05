.PHONY: setup dev frontend-dev build test eval seed index sync clean

# Pinned so everyone runs the same index. Update it when a new one is published.
INDEX_REPO := badlaldh/singlaw-vdb
INDEX_REVISION := aecbff97626c7123ce1b29fee46cae04292ab277

setup:            ## install backend + frontend deps
	cd backend && uv sync
	cd frontend && npm install

dev:              ## run the API (serves built frontend if present)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend-dev:     ## vite dev server with /api proxy → :8000
	cd frontend && npm run dev

build:            ## production frontend build
	cd frontend && npm run build

test:             ## backend test suite (stub models, offline)
	cd backend && MODEL_PROFILE=stub uv run pytest -q

# NOTE: stop `make dev` before `make eval` — embedded Qdrant is single-process
eval:             ## retrieval + grounding evaluation
	cd backend && uv run python ../eval/run_eval.py

seed:             ## load the bundled archive into Qdrant (no crawling)
	cd backend && uv run python -m app.crawler seed --archive ../data/archive

# Overwrites data/qdrant, data/db (including local chat history) and data/cache.
# Private repo: needs HF_TOKEN set in the shell. Stop the server first.
index:            ## download the published vector index into data/
	cd backend && uv run --with huggingface_hub hf download $(INDEX_REPO) --repo-type dataset \
		--revision $(INDEX_REVISION) --include "qdrant/*" --include "db/*" --include "cache/*" \
		--local-dir ../data

sync:             ## SSO incremental sync (only runs 05:00–07:00 SGT)
	cd backend && uv run python -m app.crawler sync

clean:
	rm -rf data/qdrant data/db data/cache

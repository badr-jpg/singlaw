.PHONY: setup dev frontend-dev build test eval seed sync clean

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

sync:             ## SSO incremental sync (only runs 05:00–07:00 SGT)
	cd backend && uv run python -m app.crawler sync

clean:
	rm -rf data/qdrant data/db data/cache

"""FastAPI app factory. Models, Qdrant and SQLite come up once in the
lifespan; the built React frontend is served statically when present."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import ROOT, get_settings
from app.context import build_context, shutdown_context

log = logging.getLogger(__name__)
FRONTEND_DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    log.info("loading models (profile=%s)…", settings.model_profile)
    app.state.ctx = await build_context(settings)
    log.info("ready: embedder=%s reranker=%s",
             app.state.ctx.registry.embedding_model_name,
             app.state.ctx.registry.reranker_model_name)
    yield
    await shutdown_context(app.state.ctx)


def create_app() -> FastAPI:
    app = FastAPI(title="SG Law RAG", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(api_router)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
                  name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str, request: Request):
            file = FRONTEND_DIST / path
            if path and file.is_file():
                return FileResponse(file)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.context import AppContext, shutdown_context
from app.db import Database
from app.ingest.pipeline import seed_from_archive
from app.llm import NullProvider
from app.main import create_app
from app.ml import ModelRegistry
from app.vectorstore import VectorStore

ARCHIVE = Path(__file__).resolve().parents[2] / "data" / "archive"


@pytest.fixture(scope="session")
async def ctx(tmp_path_factory) -> AppContext:
    """App context on stub models + tmp storage, seeded from the dev archive."""
    data_dir = tmp_path_factory.mktemp("data")
    settings = Settings(model_profile="stub", data_dir=data_dir, _env_file=None)
    db = Database(settings.db_path)
    await db.open()
    registry = ModelRegistry(settings)
    await registry.load()
    store = VectorStore(settings.qdrant_path)
    await store.ensure_collections(registry.embedder.dim)
    ctx = AppContext(settings=settings, db=db, store=store,
                     registry=registry, llm=NullProvider())
    await seed_from_archive(ctx, ARCHIVE)
    yield ctx
    await shutdown_context(ctx)


@pytest.fixture(scope="session")
async def client(ctx):
    """httpx client over the ASGI app, bypassing lifespan (ctx already built)."""
    app = create_app()
    app.state.ctx = ctx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as c:
        yield c

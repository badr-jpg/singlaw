"""Application context: one instance of every shared resource, built at
startup, injected everywhere. Models load exactly once (spec Part 5)."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.db import Database
from app.llm import LLMProvider, build_provider
from app.ml import ModelRegistry
from app.vectorstore import VectorStore


@dataclass
class AppContext:
    settings: Settings
    db: Database
    store: VectorStore
    registry: ModelRegistry
    llm: LLMProvider


async def build_context(settings: Settings) -> AppContext:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    await db.open()
    registry = ModelRegistry(settings)
    await registry.load()
    store = VectorStore(settings.qdrant_path)
    await store.ensure_collections(registry.embedder.dim)
    return AppContext(settings=settings, db=db, store=store,
                      registry=registry, llm=build_provider(settings))


async def shutdown_context(ctx: AppContext) -> None:
    await ctx.store.close()
    await ctx.db.close()

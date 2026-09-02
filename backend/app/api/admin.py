import asyncio
import logging

from fastapi import APIRouter, Request

from app.crawler import SSOCrawler, window_from_settings
from app.schemas import SyncRequest
from app.vectorstore import SG_LAW, USER_DOCS

router = APIRouter(tags=["ops"])
log = logging.getLogger(__name__)

_sync_task: asyncio.Task | None = None


@router.get("/health")
async def health(request: Request):
    ctx = request.app.state.ctx
    counts = await ctx.db.corpus_counts()
    return {
        "status": "ok" if ctx.registry.loaded else "degraded",
        "models": {
            "embedder": ctx.registry.embedding_model_name,
            "reranker": ctx.registry.reranker_name_active
            or ctx.registry.reranker_model_name,
            "loaded": ctx.registry.loaded,
        },
        "qdrant": {
            "sg_law": await ctx.store.count(SG_LAW),
            "user_docs": await ctx.store.count(USER_DOCS),
        },
        "corpus": {
            "acts": counts.get("act", 0),
            "subsidiary_legislation": counts.get("subsidiary_legislation", 0),
            "judgments": counts.get("judgment", 0),
            "practice_directions": counts.get("practice_direction", 0),
            "repealed": counts.get("repealed", 0),
        },
        "llm": {"provider": ctx.llm.name, "configured": ctx.llm.configured},
        "last_sync": await ctx.db.kv_get("last_sync") or await ctx.db.kv_get("last_seed"),
    }


@router.post("/admin/sync")
async def trigger_sync(req: SyncRequest, request: Request):
    """Start an SSO sync — only inside the 05:00–07:00 SGT window."""
    global _sync_task
    ctx = request.app.state.ctx
    window = window_from_settings(ctx.settings)
    if not window.is_open():
        mins = int(window.seconds_until_open() // 60)
        return {"started": False,
                "reason": f"SSO permits automated extraction only 05:00–07:00 "
                          f"Singapore Time; next window opens in ~{mins} min"}
    if _sync_task and not _sync_task.done() and not req.force:
        return {"started": False, "reason": "a sync is already running"}

    crawler = SSOCrawler(ctx)
    _sync_task = asyncio.create_task(crawler.sync())
    _sync_task.add_done_callback(
        lambda t: log.info("sync task finished: %s",
                           t.exception() or t.result()))
    return {"started": True, "reason": "sync started"}

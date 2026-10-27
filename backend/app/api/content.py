from typing import Literal

from fastapi import APIRouter, Request

from app.content import curated_suggestions, discoveries, merge_suggestions

router = APIRouter(tags=["content"])


@router.get("/content/suggestions")
async def suggestions(request: Request,
                      mode: Literal["personal", "business"] = "personal"):
    """Curated starter questions for the mode, merged with the questions real
    users asked most (>=3 identical in the last 30 days); max 4."""
    ctx = request.app.state.ctx
    curated = curated_suggestions(ctx.settings.content_dir, mode)
    popular = [r["content"] for r in await ctx.db.top_user_questions()]
    return {"suggestions": merge_suggestions(curated, popular)}


@router.get("/content/discoveries")
async def get_discoveries(request: Request):
    """Curated "did you know" items; each `question` is answered live by the RAG."""
    return {"discoveries": discoveries(request.app.state.ctx.settings.content_dir)}

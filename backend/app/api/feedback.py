from fastapi import APIRouter, HTTPException, Request

from app.schemas import FeedbackRequest

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=201)
async def post_feedback(req: FeedbackRequest, request: Request):
    """Thumbs up/down on an assistant message; one row per message (upsert)."""
    db = request.app.state.ctx.db
    if not await db.get_message(req.message_id):
        raise HTTPException(404, "message not found")
    await db.upsert_feedback(req.message_id, req.rating,
                             (req.comment or "").strip() or None)
    return {"ok": True}

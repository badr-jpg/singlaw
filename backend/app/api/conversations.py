from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas import CreateConversationRequest, RenameRequest

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(request: Request):
    return await request.app.state.ctx.db.list_conversations()


@router.post("/conversations", status_code=201)
async def create_conversation(req: CreateConversationRequest, request: Request):
    """Create an empty conversation; the UI navigates to it and then streams."""
    db = request.app.state.ctx.db
    title = (req.title or "").strip()[:120] or "New conversation"
    cid = await db.create_conversation(title=title)
    conv = await db.get_conversation(cid)
    return {k: conv[k] for k in ("id", "title", "created_at", "updated_at")} | {
        "message_count": 0}


@router.get("/conversations/{cid}")
async def get_conversation(cid: str, request: Request):
    conv = await request.app.state.ctx.db.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "conversation not found")
    return conv


@router.patch("/conversations/{cid}")
async def rename_conversation(cid: str, req: RenameRequest, request: Request):
    if not await request.app.state.ctx.db.rename_conversation(cid, req.title.strip()[:120]):
        raise HTTPException(404, "conversation not found")
    return {"ok": True}


@router.delete("/conversations/{cid}", status_code=204)
async def delete_conversation(cid: str, request: Request):
    if not await request.app.state.ctx.db.delete_conversation(cid):
        raise HTTPException(404, "conversation not found")
    return Response(status_code=204)

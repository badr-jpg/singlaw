from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.answer import chat_stream
from app.schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    ctx = request.app.state.ctx
    return StreamingResponse(
        chat_stream(ctx, req.message, req.conversation_id, req.doc_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

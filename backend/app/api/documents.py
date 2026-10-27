import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile

from app.billing import active_plan, effective_limit
from app.ingest.pipeline import delete_user_document, ingest_user_document

router = APIRouter(tags=["documents"])
log = logging.getLogger(__name__)

_ALLOWED = {".pdf", ".docx", ".txt", ".md"}
_MAX_BYTES = 25 * 1024 * 1024
_DOC_FIELDS = ("id", "filename", "status", "chunk_count", "error", "created_at",
               "business_id")


def document_view(row: dict) -> dict:
    """GET /api/documents item shape (shared with /api/businesses/{id}/documents)."""
    return {k: row.get(k) for k in _DOC_FIELDS}


@router.post("/documents")
async def upload_document(
    file: UploadFile, request: Request, business_id: str | None = Form(None),
):
    ctx = request.app.state.ctx
    suffix = Path(file.filename or "upload.txt").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(415, f"unsupported file type {suffix}; "
                                 f"allowed: {', '.join(sorted(_ALLOWED))}")
    business_id = (business_id or "").strip() or None
    if business_id and not await ctx.db.get_business(business_id):
        raise HTTPException(404, "business not found")
    plan = await active_plan(ctx.db)
    doc_limit = effective_limit(plan["limits"]["documents"], 0)
    if doc_limit is not None:
        existing = len(await ctx.db.list_user_documents(ctx.settings.user_id))
        if existing >= doc_limit:
            raise HTTPException(
                403, f"Plan limit reached: the {plan['name']} plan allows {doc_limit} "
                     "uploaded documents. Delete one or upgrade your plan.")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "file exceeds the 25 MB limit")

    filename = Path(file.filename or "upload.txt").name
    did = await ctx.db.add_user_document(ctx.settings.user_id, filename, "",
                                         business_id=business_id)
    dest_dir = ctx.settings.data_dir / "uploads" / did
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(data)
    await ctx.db.set_document_path(did, str(dest))

    task = asyncio.create_task(ingest_user_document(ctx, did))
    task.add_done_callback(lambda t: t.exception())  # surface via logs, don't crash
    return {"id": did, "filename": filename, "status": "pending",
            "business_id": business_id}


@router.get("/documents")
async def list_documents(request: Request):
    ctx = request.app.state.ctx
    rows = await ctx.db.list_user_documents(ctx.settings.user_id)
    return [document_view(r) for r in rows]


@router.delete("/documents/{did}", status_code=204)
async def delete_document(did: str, request: Request):
    if not await delete_user_document(request.app.state.ctx, did):
        raise HTTPException(404, "document not found")
    return Response(status_code=204)

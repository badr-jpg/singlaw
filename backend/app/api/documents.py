import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile

from app.ingest.pipeline import ingest_user_document
from app.vectorstore import USER_DOCS

router = APIRouter(tags=["documents"])
log = logging.getLogger(__name__)

_ALLOWED = {".pdf", ".docx", ".txt", ".md"}
_MAX_BYTES = 25 * 1024 * 1024


@router.post("/documents")
async def upload_document(file: UploadFile, request: Request):
    ctx = request.app.state.ctx
    suffix = Path(file.filename or "upload.txt").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(415, f"unsupported file type {suffix}; "
                                 f"allowed: {', '.join(sorted(_ALLOWED))}")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "file exceeds the 25 MB limit")

    filename = Path(file.filename or "upload.txt").name
    did = await ctx.db.add_user_document(ctx.settings.user_id, filename, "")
    dest_dir = ctx.settings.data_dir / "uploads" / did
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(data)
    await ctx.db.set_document_path(did, str(dest))

    task = asyncio.create_task(ingest_user_document(ctx, did))
    task.add_done_callback(lambda t: t.exception())  # surface via logs, don't crash
    return {"id": did, "filename": filename, "status": "pending"}


@router.get("/documents")
async def list_documents(request: Request):
    ctx = request.app.state.ctx
    rows = await ctx.db.list_user_documents(ctx.settings.user_id)
    return [{k: r[k] for k in
             ("id", "filename", "status", "chunk_count", "error", "created_at")}
            for r in rows]


@router.delete("/documents/{did}", status_code=204)
async def delete_document(did: str, request: Request):
    ctx = request.app.state.ctx
    row = await ctx.db.get_user_document(did)
    if not row:
        raise HTTPException(404, "document not found")
    await ctx.store.delete_doc(USER_DOCS, f"user-{did}")
    await ctx.db.delete_user_document(did)
    if row.get("path"):
        shutil.rmtree(Path(row["path"]).parent, ignore_errors=True)
    return Response(status_code=204)

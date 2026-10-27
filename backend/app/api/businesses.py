"""Business workspaces: a named profile plus its own uploaded documents.
Chat scoped with `business_id` searches those documents and passes the
profile to generation as factual context (never authority)."""
from fastapi import APIRouter, HTTPException, Request, Response

from app.api.documents import document_view
from app.billing import active_plan, effective_limit
from app.ingest.pipeline import delete_user_document
from app.schemas import BusinessCreate, BusinessUpdate

router = APIRouter(tags=["businesses"])

_FIELDS = ("id", "name", "description", "icon", "document_count", "created_at")


def _view(row: dict) -> dict:
    return {k: row[k] for k in _FIELDS}


@router.get("/businesses")
async def list_businesses(request: Request):
    ctx = request.app.state.ctx
    return [_view(b) for b in await ctx.db.list_businesses(ctx.settings.user_id)]


@router.post("/businesses", status_code=201)
async def create_business(req: BusinessCreate, request: Request):
    ctx = request.app.state.ctx
    plan = await active_plan(ctx.db)
    limit = effective_limit(plan["limits"]["businesses"], ctx.settings.max_businesses)
    if limit is not None and await ctx.db.count_businesses(ctx.settings.user_id) >= limit:
        raise HTTPException(
            403, f"Plan limit reached: the {plan['name']} plan allows {limit} "
                 f"business workspace{'s' if limit != 1 else ''}. "
                 "Delete one or upgrade your plan.")
    name = req.name.strip()
    if not name:
        raise HTTPException(422, "name cannot be blank")
    bid = await ctx.db.create_business(
        ctx.settings.user_id, name, req.description.strip(),
        req.icon.strip() or "Building2")
    return _view(await ctx.db.get_business(bid))


@router.patch("/businesses/{bid}")
async def update_business(bid: str, req: BusinessUpdate, request: Request):
    ctx = request.app.state.ctx
    fields = {k: v.strip() if isinstance(v, str) else v
              for k, v in req.model_dump(exclude_unset=True).items()}
    if fields.get("name") == "":
        raise HTTPException(422, "name cannot be blank")
    if fields.get("icon") == "":
        fields["icon"] = "Building2"
    if not await ctx.db.update_business(bid, **fields):
        raise HTTPException(404, "business not found")
    return _view(await ctx.db.get_business(bid))


@router.delete("/businesses/{bid}", status_code=204)
async def delete_business(bid: str, request: Request):
    """Deletes the business AND its documents (Qdrant points, files, rows)."""
    ctx = request.app.state.ctx
    if not await ctx.db.get_business(bid):
        raise HTTPException(404, "business not found")
    for doc in await ctx.db.list_user_documents(ctx.settings.user_id, business_id=bid):
        await delete_user_document(ctx, doc["id"])
    await ctx.db.delete_business(bid)
    return Response(status_code=204)


@router.get("/businesses/{bid}/documents")
async def business_documents(bid: str, request: Request):
    ctx = request.app.state.ctx
    if not await ctx.db.get_business(bid):
        raise HTTPException(404, "business not found")
    rows = await ctx.db.list_user_documents(ctx.settings.user_id, business_id=bid)
    return [document_view(r) for r in rows]

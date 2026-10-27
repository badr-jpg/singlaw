from fastapi import APIRouter, HTTPException, Request

from app.retrieval import retrieve
from app.schemas import SearchRequest

router = APIRouter(tags=["search"])


@router.post("/search")
async def search(req: SearchRequest, request: Request):
    """Retrieval only, no generation — debugging and power users."""
    ctx = request.app.state.ctx
    doc_ids = list(req.doc_ids or [])
    if req.business_id:
        if not await ctx.db.get_business(req.business_id):
            raise HTTPException(404, "business not found")
        rows = await ctx.db.list_user_documents(ctx.settings.user_id,
                                                business_id=req.business_id)
        doc_ids = list(dict.fromkeys([*doc_ids, *(r["id"] for r in rows)]))
    result = await retrieve(ctx, req.query, doc_ids=doc_ids or None, top_k=req.top_k)
    return {
        "results": [
            {
                "chunk_id": c.payload.chunk_id,
                "citation": c.payload.citation,
                "url": c.payload.source_url,
                "doc_type": c.payload.doc_type,
                "authority_tier": c.payload.authority_tier,
                "status": c.payload.status,
                "treatment": c.payload.treatment,
                "court": c.payload.court,
                "decision_date": c.payload.decision_date.isoformat()
                if c.payload.decision_date else None,
                "hierarchy_path": c.payload.hierarchy_path,
                "collection": c.payload.collection,
                "snippet": c.payload.text[:240],
                "text": c.payload.text,
                "pinned": c.pinned,
                "rrf_score": round(c.rrf_score, 5),
                "ce_score": round(c.ce_score, 5),
                "authority_score": round(c.authority_score, 4),
                "final_score": round(c.final_score, 4),
            }
            for c in result.chunks
        ],
        "low_confidence": result.low_confidence,
        "low_confidence_reasons": result.low_confidence_reasons,
        "filtered": result.filtered.model_dump(),
        "intent": result.analysis.intent,
        "debug": result.debug.model_dump() if req.include_debug else None,
    }

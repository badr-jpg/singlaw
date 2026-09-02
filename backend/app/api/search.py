from fastapi import APIRouter, Request

from app.retrieval import retrieve
from app.schemas import SearchRequest

router = APIRouter(tags=["search"])


@router.post("/search")
async def search(req: SearchRequest, request: Request):
    """Retrieval only, no generation — debugging and power users."""
    ctx = request.app.state.ctx
    result = await retrieve(ctx, req.query, doc_ids=req.doc_ids, top_k=req.top_k)
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

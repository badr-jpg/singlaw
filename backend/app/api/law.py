"""Direct law lookup and the corpus explorer endpoints."""
from fastapi import APIRouter, HTTPException, Request

from app.ingest.chunker import slugify
from app.ingest.citations import extract_neutral_citations
from app.retrieval import _STATUTE_CITE_RX, resolve_citations
from app.vectorstore import SG_LAW

router = APIRouter(tags=["law"])


def _chunk_view(payload: dict) -> dict:
    """Contract shape: source fields (url, snippet, …) + text/context/doc_id."""
    return {
        "n": 0,
        "chunk_id": payload.get("chunk_id"),
        "doc_id": payload.get("doc_id"),
        "citation": payload.get("citation", ""),
        "url": payload.get("source_url", ""),
        "doc_type": payload.get("doc_type"),
        "authority_tier": payload.get("authority_tier"),
        "status": payload.get("status"),
        "treatment": payload.get("treatment", "unknown"),
        "court": payload.get("court"),
        "decision_date": payload.get("decision_date"),
        "hierarchy_path": payload.get("hierarchy_path") or [],
        "snippet": (payload.get("text") or "")[:240],
        "collection": payload.get("collection", "sg_law"),
        "text": payload.get("text", ""),
        "context": payload.get("context", ""),
    }


async def _doc_id_for_citation(ctx, citation: str) -> str | None:
    neutral = extract_neutral_citations(citation)
    if neutral:
        j = await ctx.db.get_judgment(neutral[0])
        return j["doc_id"] if j else None
    m = _STATUTE_CITE_RX.match(citation)
    title = m.group(1).strip() if m else citation.strip()
    doc = await ctx.db.get_corpus_doc(slugify(title))
    return doc["doc_id"] if doc else None


@router.get("/law/{citation}")
async def get_law(citation: str, request: Request):
    ctx = request.app.state.ctx
    pinned = await resolve_citations(ctx, [citation])
    payloads = [c.payload.model_dump(mode="json") for c in pinned]
    if not payloads:
        # bare Act name: return the whole document's chunks
        doc_id = await _doc_id_for_citation(ctx, citation)
        if doc_id:
            payloads = await ctx.store.by_doc_id(SG_LAW, doc_id)
            payloads.sort(key=lambda p: str(p.get("chunk_id", "")))
    return {"found": bool(payloads), "chunks": [_chunk_view(p) for p in payloads]}


@router.get("/law/{citation}/history")
async def law_history(citation: str, request: Request):
    ctx = request.app.state.ctx
    doc_id = await _doc_id_for_citation(ctx, citation)
    if not doc_id:
        raise HTTPException(404, "no document found for that citation")
    return {"versions": await ctx.db.doc_versions(doc_id)}


@router.get("/law/{citation}/citing")
async def law_citing(citation: str, request: Request):
    ctx = request.app.state.ctx
    rows = await ctx.db.citing_of(citation)
    return {"citing": [
        {"citation": r["citation"], "case_name": r.get("case_name"),
         "court": r.get("court_code"), "decision_date": r.get("decision_date"),
         "treatment": r["treatment_hint"], "paragraph": r.get("paragraph")}
        for r in rows]}


@router.get("/corpus/toc")
async def corpus_toc(request: Request, q: str | None = None,
                     doc_type: str | None = None):
    rows = await request.app.state.ctx.db.list_corpus(q=q, doc_type=doc_type)
    return [{k: r[k] for k in ("doc_id", "title", "citation", "doc_type",
                               "status", "authority_tier")} for r in rows]


@router.get("/corpus/doc/{doc_id}")
async def corpus_doc(doc_id: str, request: Request):
    ctx = request.app.state.ctx
    doc = await ctx.db.get_corpus_doc(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    payloads = await ctx.store.by_doc_id(SG_LAW, doc_id)
    payloads.sort(key=lambda p: str(p.get("chunk_id", "")))

    # hierarchy_path is [title, (Part…), (Division…), Section…/Paragraphs…]
    root: list[dict] = []
    index: dict[tuple, dict] = {}
    for p in payloads:
        path = p.get("hierarchy_path") or [doc["title"]]
        parents = path[1:-1]
        leaf_label = path[-1] if len(path) > 1 else p.get("citation", "chunk")
        children = root
        key: tuple = ()
        for part in parents:
            key = key + (part,)
            node = index.get(key)
            if node is None:
                node = {"label": part, "citation": None, "chunk_id": None,
                        "children": []}
                index[key] = node
                children.append(node)
            children = node["children"]
        children.append({"label": leaf_label, "citation": p.get("citation"),
                         "chunk_id": p.get("chunk_id"), "children": []})
    return {"doc_id": doc_id, "title": doc["title"], "citation": doc["citation"],
            "doc_type": doc["doc_type"], "status": doc["status"],
            "source_url": doc["source_url"],
            "sso_version_date": doc["sso_version_date"], "tree": root}


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str, request: Request):
    payload = await request.app.state.ctx.store.get_chunk(chunk_id)
    if payload is None:
        raise HTTPException(404, "chunk not found")
    return _chunk_view(payload)

"""The retrieval pipeline (spec Part 3), stages 1–9:

analysis → citation short-circuit → rewrites + HyDE → parallel dense+sparse →
RRF → hard status filters (counted, never silent) → cross-encoder rerank →
authority-aware final rank → coverage check.

Works fully offline: without an LLM, analysis degrades to regex heuristics
and rewriting/HyDE are skipped.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from datetime import date

from qdrant_client import models

from app.context import AppContext
from app.ingest.chunker import slugify
from app.ingest.citations import (
    NEUTRAL_RX,
    SECTION_REF_RX,
    extract_neutral_citations,
)
from app.llm import parse_json_reply
from app.schemas import (
    ChunkPayload,
    FilteredCounts,
    QueryAnalysis,
    RetrievalDebug,
    RetrievalResult,
    RetrievedChunk,
)
from app.vectorstore import SG_LAW, USER_DOCS

log = logging.getLogger(__name__)


async def _cached_llm(ctx: AppContext, kind: str, query: str, producer):
    """Persist helper-call results per normalised question (SQLite kv).

    Analysis, rewrites and HyDE depend only on the question text, and each
    costs a 5–15 s reasoning-model round-trip — repeated and trending
    questions should pay that once."""
    norm = " ".join(query.lower().split())
    key = "llmcache:" + hashlib.sha256(
        f"{kind}|{ctx.settings.llm_fast_model}|{norm}".encode()).hexdigest()
    hit = await ctx.db.kv_get(key)
    if hit is not None:
        return json.loads(hit)
    value = await producer()
    if value not in (None, [], ""):
        await ctx.db.kv_set(key, json.dumps(value))
    return value

# authority_tier → score for the final blend (tunable; logged per result)
TIER_SCORE = {1: 1.0, 2: 0.92, 3: 0.8, 4: 0.75, 5: 0.55, 6: 0.35}

# ---------------------------------------------------------------- stage 1

_TEMPORAL_RX = re.compile(
    r"\b(?:in|as at|as of|back in|during|before)\s+((?:19|20)\d{2})\b.*?"
    r"|\bwhat was the law\b.*?\b((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_REPEALED_ASK_RX = re.compile(r"\brepealed|former|old law|previous(?:ly)?\b", re.IGNORECASE)
_DRAFTING_RX = re.compile(
    r"\b(?:draft|write|prepare|generate)\b.{0,40}\b(?:letter of demand|affidavit|"
    r"statement of claim|defence|writ|summons|originating (?:claim|application)|"
    r"contract|will|deed|notice to quit|court (?:form|document)|submission)",
    re.IGNORECASE,
)
_CASELAW_RX = re.compile(r"\bcase law|judgment|precedent|court (?:held|decided)|authorit", re.IGNORECASE)
# offline backstop only — the LLM's scope verdict overrides this when configured.
# Requires a named foreign jurisdiction NEAR a legal-ish term, to avoid tripping
# on e.g. "my US employer's Singapore branch".
_FOREIGN_RX = re.compile(
    r"\b(?:malaysia[n]?|united kingdom|UK|british|england|india[n]?|australia[n]?|"
    r"hong kong|US|united states|california|new york)\b"
    r"[^.?!]{0,40}\b(?:law|act|statute|visa|court|fine|divorce|wage|tax|tenancy)",
    re.IGNORECASE)
_PROCEDURAL_RX = re.compile(r"\bhow (?:do|to) (?:i|we) (?:file|sue|appeal|serve)|procedure|deadline|time limit|form\b", re.IGNORECASE)

_ANALYSIS_PROMPT = """You classify legal research queries for a Singapore law retrieval system.
Reply with ONLY a JSON object:
{{
  "intent": "statutory_lookup" | "procedural" | "rights_obligations" | "case_law" | "out_of_scope",
  "citations": [<explicit statutory or case citations named in the query, canonicalised like "Employment Act 1968, s 14(2)" or "[2022] SGCA 60">],
  "temporal_year": <int year if the user asks about the law at a past point in time, else null>,
  "include_repealed": <true if the user explicitly asks about repealed/former law>,
  "out_of_scope": <true if the question is not about Singapore law at all (other jurisdictions, non-legal topics)>,
  "out_of_scope_reason": "<one short sentence, empty if in scope>",
  "wants_drafting": <true if the user asks you to draft a document to file in court or serve on another party>
}}

Query: {query}"""


def analyze_heuristic(query: str) -> QueryAnalysis:
    a = QueryAnalysis()
    a.citations = extract_neutral_citations(query)
    for m in SECTION_REF_RX.finditer(query):
        a.citations.append(f"{m.group(2)}, s {m.group(1)}")
    if m := _TEMPORAL_RX.search(query):
        year = m.group(1) or m.group(2)
        if year and int(year) < date.today().year:
            a.temporal_anchor = date(int(year), 12, 31)
    a.include_repealed = bool(_REPEALED_ASK_RX.search(query))
    a.wants_drafting = bool(_DRAFTING_RX.search(query))
    if _FOREIGN_RX.search(query) and "singapore" not in query.lower():
        a.out_of_scope = True
        a.out_of_scope_reason = "it appears to concern another jurisdiction"
    if a.citations:
        a.intent = "statutory_lookup"
    elif _CASELAW_RX.search(query):
        a.intent = "case_law"
    elif _PROCEDURAL_RX.search(query):
        a.intent = "procedural"
    return a


async def analyze_query(ctx: AppContext, query: str) -> QueryAnalysis:
    a = analyze_heuristic(query)
    if not ctx.llm.configured:
        return a
    cached = await _cached_llm(ctx, "analysis", query,
                               lambda: _analyze_with_llm(ctx, query, a))
    return QueryAnalysis.model_validate(cached) if isinstance(cached, dict) else a


async def _analyze_with_llm(ctx: AppContext, query: str, a: QueryAnalysis) -> dict:
    try:
        reply = await ctx.llm.complete(
            [{"role": "user", "content": _ANALYSIS_PROMPT.format(query=query)}],
            max_tokens=3000, temperature=0.0, model=ctx.settings.llm_fast_model or None)  # room for reasoning-model thinking
    except Exception as exc:
        log.warning("query analysis LLM call failed, using heuristics: %s", exc)
        return a.model_dump(mode="json")
    data = parse_json_reply(reply)
    if not data:
        return a.model_dump(mode="json")
    if data.get("intent") in ("statutory_lookup", "procedural",
                              "rights_obligations", "case_law", "out_of_scope"):
        a.intent = data["intent"]
    for c in data.get("citations") or []:
        if isinstance(c, str) and c not in a.citations:
            a.citations.append(c)
    if isinstance(data.get("temporal_year"), int) and a.temporal_anchor is None:
        a.temporal_anchor = date(data["temporal_year"], 12, 31)
    a.include_repealed = a.include_repealed or bool(data.get("include_repealed"))
    a.out_of_scope = bool(data.get("out_of_scope"))
    a.out_of_scope_reason = str(data.get("out_of_scope_reason") or "")
    a.wants_drafting = a.wants_drafting or bool(data.get("wants_drafting"))
    return a.model_dump(mode="json")


# ---------------------------------------------------------------- stage 2

_STATUTE_CITE_RX = re.compile(r"^(.*\bAct\s+\d{4}),\s*s\s+(\d+[A-Z]{0,2})")


async def resolve_citations(ctx: AppContext, citations: list[str]) -> list[RetrievedChunk]:
    """Fetch explicitly named provisions/cases directly and pin at rank 0 —
    semantic search must not be asked to rediscover them."""
    pinned: list[RetrievedChunk] = []
    seen: set[str] = set()

    async def add(payloads: list[dict]) -> None:
        for p in payloads:
            try:
                cp = ChunkPayload.model_validate(p)
            except Exception:
                continue
            if cp.chunk_id not in seen:
                seen.add(cp.chunk_id)
                pinned.append(RetrievedChunk(payload=cp, pinned=True))

    for cite in citations:
        if NEUTRAL_RX.search(cite):
            neutral = extract_neutral_citations(cite)
            if not neutral:
                continue
            j = await ctx.db.get_judgment(neutral[0])
            if j:
                payloads = await ctx.store.by_doc_id(SG_LAW, j["doc_id"])
                await add(sorted(payloads, key=lambda p: p.get("chunk_id", ""))[:2])
            continue
        m = _STATUTE_CITE_RX.match(cite)
        if not m:
            continue
        act_title, sec = m.group(1).strip(), m.group(2)
        exact = await ctx.store.by_citation_exact(f"{act_title}, s {sec}")
        if exact:
            await add(exact)
            continue
        # split sections ("s 14(1)–(2)") or title variants: match within the doc
        payloads = await ctx.store.by_doc_id(SG_LAW, slugify(act_title))
        await add([
            p for p in payloads
            if str(p.get("chunk_id", "")).split(":", 1)[-1] == f"s{sec}"
            or str(p.get("chunk_id", "")).split(":", 1)[-1].startswith(f"s{sec}(")
        ])
    return pinned


# ---------------------------------------------------------------- stage 3

_REWRITE_PROMPT = """Rewrite the layperson's legal question below for a Singapore law search engine whose corpus uses formal statutory language. Give {n} short rephrasings (one line each) using Singapore legal terms of art and likely Act names — one statutory, one rights/duties, one procedural or case-law angle.
Reply with ONLY a JSON array of {n} strings. No explanation.

Question: {query}"""

_HYDE_PROMPT = """Write one short passage (at most 60 words) in the style of a Singapore statutory provision or judgment paragraph that would directly answer the question below. Formal legislative register; do not invent section numbers or case names. Reply with the passage only.

Question: {query}"""


async def rewrite_queries(ctx: AppContext, query: str) -> list[str]:
    if not ctx.llm.configured:
        return []
    return await _cached_llm(ctx, "rewrites", query, lambda: _rewrite_with_llm(ctx, query))


async def _rewrite_with_llm(ctx: AppContext, query: str) -> list[str]:
    try:
        reply = await ctx.llm.complete(
            [{"role": "user", "content": _REWRITE_PROMPT.format(
                n=ctx.settings.n_rewrites, query=query)}],
            max_tokens=2000, temperature=0.3, model=ctx.settings.llm_fast_model or None)
    except Exception as exc:
        log.warning("rewrite LLM call failed: %s", exc)
        return []
    cleaned = _strip_fences(reply)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        lo, hi = cleaned.find("["), cleaned.rfind("]")
        try:
            data = json.loads(cleaned[lo:hi + 1]) if 0 <= lo < hi else []
        except json.JSONDecodeError:
            data = []
    return [r.strip() for r in data if isinstance(r, str) and r.strip()][: ctx.settings.n_rewrites]


async def hyde_passage(ctx: AppContext, query: str) -> str | None:
    if not ctx.llm.configured:
        return None
    return await _cached_llm(ctx, "hyde", query, lambda: _hyde_with_llm(ctx, query))


async def _hyde_with_llm(ctx: AppContext, query: str) -> str | None:
    try:
        reply = await ctx.llm.complete(
            [{"role": "user", "content": _HYDE_PROMPT.format(query=query)}],
            max_tokens=2000, temperature=0.3, model=ctx.settings.llm_fast_model or None)
    except Exception as exc:
        log.warning("HyDE LLM call failed: %s", exc)
        return None
    text = _strip_fences(reply).strip().strip('"')
    return text or None


async def rewrite_and_hyde(ctx: AppContext, query: str) -> tuple[list[str], str | None]:
    """Query rewrites and a HyDE passage, as two small concurrent LLM calls.
    One combined JSON call cost 25–40 s on reasoning models; two terse calls
    run in parallel finish in a fraction of that."""
    rewrites, hyde = await asyncio.gather(rewrite_queries(ctx, query), hyde_passage(ctx, query))
    return rewrites, hyde


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)


# ---------------------------------------------------------------- stages 4–5

def rrf_fuse(rankings: list[list[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


async def _hybrid_search(
    ctx: AppContext, queries: list[str], hyde: str | None,
    collection: str, flt: models.Filter | None, top_k: int,
) -> tuple[dict[str, ChunkPayload], dict[str, float]]:
    """Parallel dense+sparse for every query variant (+ HyDE dense), RRF-fused."""
    dense_qs = await ctx.registry.embed_queries(queries)
    sparse_qs = [await asyncio.to_thread(ctx.registry.sparse.encode_query, q)
                 for q in queries]

    tasks = []
    for i in range(len(queries)):
        tasks.append(ctx.store.search_dense(collection, dense_qs[i], top_k, flt))
        tasks.append(ctx.store.search_sparse(collection, sparse_qs[i], top_k, flt))
    if hyde:
        hyde_vec = (await ctx.registry.embed_docs([hyde]))[0]
        tasks.append(ctx.store.search_dense(collection, hyde_vec, top_k, flt))

    result_lists = await asyncio.gather(*tasks)
    payloads: dict[str, ChunkPayload] = {}
    rankings: list[list[str]] = []
    for points in result_lists:
        ranking = []
        for pt in points:
            try:
                cp = ChunkPayload.model_validate(pt.payload)
            except Exception:
                continue
            payloads[cp.chunk_id] = cp
            ranking.append(cp.chunk_id)
        rankings.append(ranking)
    return payloads, rrf_fuse(rankings, ctx.settings.rrf_k)


# ---------------------------------------------------------------- stage 6

def apply_hard_filters(
    chunks: list[RetrievedChunk], analysis: QueryAnalysis,
) -> tuple[list[RetrievedChunk], FilteredCounts]:
    """Exclude non-in-force law unless the query anchors to the past or asks
    for repealed law. Counted, never silent (spec stage 6)."""
    counts = FilteredCounts()
    if analysis.include_repealed:
        return chunks, counts

    kept: list[RetrievedChunk] = []
    anchor = analysis.temporal_anchor
    for rc in chunks:
        p = rc.payload
        if p.collection != "sg_law" or rc.pinned:
            kept.append(rc)  # user facts and explicit citations are never dropped
            continue
        if anchor is not None:
            if p.doc_type == "judgment":
                if p.decision_date and p.decision_date > anchor:
                    counts.not_yet_commenced += 1
                    continue
            else:
                if p.in_force_from and p.in_force_from > anchor:
                    counts.not_yet_commenced += 1
                    continue
                if p.in_force_to and p.in_force_to < anchor:
                    counts.repealed += 1
                    continue
            kept.append(rc)
            continue
        if p.status == "repealed":
            counts.repealed += 1
        elif p.status == "spent":
            counts.spent += 1
        elif p.status == "not_yet_commenced":
            counts.not_yet_commenced += 1
        else:
            kept.append(rc)
    return kept, counts


# ---------------------------------------------------------------- stages 7–8

def _sigmoid_if_logit(scores: list[float]) -> list[float]:
    """Cross-encoders differ: some emit probabilities, some raw logits.
    Map to (0,1) only when values fall outside [0,1]."""
    if scores and (min(scores) < 0 or max(scores) > 1):
        return [1.0 / (1.0 + math.exp(-s)) for s in scores]
    return scores


def _recency(p: ChunkPayload, today: date) -> float:
    if p.doc_type == "judgment":
        if not p.decision_date:
            return 0.5
        years = max(0.0, (today - p.decision_date).days / 365.25)
        return max(0.0, 1.0 - years / 25.0)
    if p.status == "in_force":
        return 1.0  # current consolidated text
    return 0.2


def authority_rank(
    ctx: AppContext, chunks: list[RetrievedChunk], today: date | None = None,
) -> list[RetrievedChunk]:
    """Blend cross-encoder score with authority tier and recency (stage 8).
    Both raw scores are kept on the chunk and logged for tuning."""
    s = ctx.settings
    today = today or date.today()
    # rank-percentile CE component: scale-robust across rerankers (raw logits
    # saturate a sigmoid; min-max amplifies small gaps and let a high-CE
    # overruled case outrank binding authority). The coverage check uses the
    # absolute (sigmoid) score separately.
    order = sorted(range(len(chunks)), key=lambda i: -chunks[i].ce_score)
    n = len(chunks)
    for pos, i in enumerate(order):
        chunks[i].ce_norm = (1.0 - pos / (n - 1)) if n > 1 else 1.0
    for c in chunks:
        if c.payload.collection == "user_docs":
            # the user's facts, not authority: rank purely on relevance
            c.authority_score, c.recency_score = 0.0, 0.0
            c.final_score = c.ce_norm
            continue
        c.authority_score = TIER_SCORE.get(c.payload.authority_tier, 0.3)
        if c.payload.treatment == "overruled":
            c.authority_score *= 0.25
        c.recency_score = _recency(c.payload, today)
        c.final_score = (s.w_cross_encoder * c.ce_norm
                         + s.w_authority * c.authority_score
                         + s.w_recency * c.recency_score)
    ordered = sorted(chunks, key=lambda c: (not c.pinned, -c.final_score))
    for c in ordered[:10]:
        log.info("rank %-60s ce=%.4f ce_norm=%.3f auth=%.2f rec=%.2f final=%.3f%s",
                 c.payload.citation[:60], c.ce_score, c.ce_norm, c.authority_score,
                 c.recency_score, c.final_score, " [pinned]" if c.pinned else "")
    return ordered


# ---------------------------------------------------------------- stage 9

def coverage_check(
    ctx: AppContext, chunks: list[RetrievedChunk], filtered: FilteredCounts,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not chunks:
        reasons.append("all_results_filtered" if filtered.total else "no_results")
        return True, reasons
    law = [c for c in chunks if c.payload.collection == "sg_law"]
    if not law:
        reasons.append("no_authoritative_sources")
        return True, reasons
    top = _sigmoid_if_logit([c.ce_score for c in law[:3]])
    if max(top) < ctx.settings.low_confidence_threshold and not law[0].pinned:
        reasons.append("weak_relevance")
    for i, c in enumerate(law[:5]):
        if c.payload.treatment != "overruled":
            continue
        # an overruled case is only alarming when nothing better sits above
        # it — if the overruling/binding authority already outranks it, the
        # conflict is resolved and the source badge is warning enough
        better_above = any(
            x.payload.treatment != "overruled" and x.payload.authority_tier <= 4
            for x in law[:i])
        if not better_above:
            reasons.append("overruled_authority_in_top_results")
        break
    top_law = law[0].payload
    if top_law.authority_tier >= 6 and any(
            c.payload.authority_tier <= 3 for c in law[1:5]):
        reasons.append("guidance_outranks_legislation")
    return bool(reasons), reasons


# ---------------------------------------------------------------- pipeline

async def retrieve(
    ctx: AppContext, query: str, *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
    analysis: QueryAnalysis | None = None,
    rewrites: list[str] | None = None,
    hyde: str | None = None,
) -> RetrievalResult:
    s = ctx.settings
    t0 = time.perf_counter()
    debug = RetrievalDebug()
    timings = debug.timings_ms

    if analysis is None:
        analysis = await analyze_query(ctx, query)
    timings["analysis"] = (time.perf_counter() - t0) * 1000

    pinned = await resolve_citations(ctx, analysis.citations)
    debug.citation_shortcircuit = [c.payload.citation for c in pinned]
    t1 = time.perf_counter()
    timings["citation_shortcircuit"] = (t1 - t0) * 1000 - timings["analysis"]

    if rewrites is None:  # callers may precompute these concurrently with analysis
        rewrites, hyde = await rewrite_and_hyde(ctx, query)
    debug.rewrites, debug.hyde = rewrites, hyde
    queries = [query] + rewrites
    t2 = time.perf_counter()
    timings["rewrite_hyde"] = (t2 - t1) * 1000

    payloads, fused = await _hybrid_search(
        ctx, queries, hyde, SG_LAW, None, s.top_k_per_list)

    user_filter: models.Filter | None = None
    conditions = [models.FieldCondition(
        key="user_id", match=models.MatchValue(value=s.user_id))]
    if doc_ids:
        conditions.append(models.FieldCondition(
            key="doc_id", match=models.MatchAny(any=[f"user-{d}" for d in doc_ids])))
    user_filter = models.Filter(must=conditions)
    user_payloads, user_fused = await _hybrid_search(
        ctx, queries, None, USER_DOCS, user_filter, s.user_docs_top_k)
    t3 = time.perf_counter()
    timings["hybrid_search"] = (t3 - t2) * 1000

    pinned_ids = {c.payload.chunk_id for c in pinned}
    fused_sorted = sorted(fused.items(), key=lambda kv: -kv[1])[: s.fusion_top]
    candidates = list(pinned)
    for cid, score in fused_sorted:
        if cid not in pinned_ids:
            candidates.append(RetrievedChunk(payload=payloads[cid], rrf_score=score))
    for cid, score in sorted(user_fused.items(), key=lambda kv: -kv[1])[: s.user_docs_top_k]:
        candidates.append(RetrievedChunk(payload=user_payloads[cid], rrf_score=score))
    debug.candidates_pre_filter = len(candidates)
    debug.candidates_pre_rerank = [
        {"chunk_id": c.payload.chunk_id, "citation": c.payload.citation,
         "rrf_score": round(c.rrf_score, 5)}
        for c in candidates[:50]]

    candidates, filtered = apply_hard_filters(candidates, analysis)
    t4 = time.perf_counter()
    timings["fusion_filters"] = (t4 - t3) * 1000

    texts = [f"{c.payload.citation}\n{c.payload.context}\n{c.payload.text[:1500]}"
             for c in candidates]
    scores = await ctx.registry.rerank(query, texts)
    for c, sc in zip(candidates, scores):
        c.ce_score = float(sc)
    candidates.sort(key=lambda c: (not c.pinned, -c.ce_score))
    candidates = candidates[: s.rerank_top]
    t5 = time.perf_counter()
    timings["rerank"] = (t5 - t4) * 1000

    ranked = authority_rank(ctx, candidates)
    ranked = ranked[: top_k or s.final_top]
    low_conf, reasons = coverage_check(ctx, ranked, filtered)
    timings["total"] = (time.perf_counter() - t0) * 1000

    return RetrievalResult(
        chunks=ranked, analysis=analysis, filtered=filtered,
        low_confidence=low_conf, low_confidence_reasons=reasons, debug=debug)

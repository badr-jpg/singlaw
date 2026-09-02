from datetime import date

from app.retrieval import analyze_heuristic, retrieve, rrf_fuse


def test_rrf_fuse_math():
    scores = rrf_fuse([["a", "b"], ["a", "c"]], k=60)
    assert scores["a"] > scores["b"] == scores["c"]
    assert abs(scores["a"] - 2 / 61) < 1e-9


def test_heuristic_analysis_extracts_citations_and_time():
    a = analyze_heuristic("What did s 14 of the Employment Act 1968 require in 2019?")
    assert "Employment Act 1968, s 14" in a.citations
    assert a.temporal_anchor == date(2019, 12, 31)
    assert a.intent == "statutory_lookup"


def test_heuristic_analysis_detects_drafting():
    a = analyze_heuristic("Please draft a letter of demand to my landlord")
    assert a.wants_drafting


async def test_citation_shortcircuit_pins_rank_zero(ctx):
    r = await retrieve(ctx, "What does s 14 of the Employment Act 1968 say about misconduct?")
    assert r.chunks and r.chunks[0].pinned
    assert r.chunks[0].payload.citation == "Employment Act 1968, s 14"
    assert "Employment Act 1968, s 14" in r.debug.citation_shortcircuit


async def test_hybrid_retrieval_surfaces_relevant_law(ctx):
    r = await retrieve(ctx, "can my employer dismiss me for misconduct without an inquiry")
    top_citations = [c.payload.citation for c in r.chunks[:5]]
    assert any("Employment Act 1968, s 14" in c for c in top_citations) or \
           any("[2022] SGCA 60" in c for c in top_citations)


async def test_repealed_law_filtered_and_counted(ctx):
    r = await retrieve(ctx, "is an innkeeper liable for loss of goods brought to the inn")
    assert r.filtered.repealed >= 1
    assert not any("Innkeepers" in c.payload.citation for c in r.chunks)


async def test_temporal_anchor_restores_repealed_law(ctx):
    r = await retrieve(ctx, "what was the law on innkeeper liability for guests' goods in 2019")
    assert any("Innkeepers" in c.payload.citation for c in r.chunks)
    # and post-anchor judgments are excluded
    assert not any(c.payload.decision_date and c.payload.decision_date.year > 2019
                   for c in r.chunks if c.payload.doc_type == "judgment")


async def test_authority_blend_prefers_binding_court(ctx):
    r = await retrieve(ctx, "must an employer hold a due inquiry before dismissal for misconduct")
    law = [c for c in r.chunks if c.payload.doc_type == "judgment"]
    if len(law) >= 2:
        pos = {c.payload.citation.split(" at ")[0]: i for i, c in enumerate(law)}
        if "[2022] SGCA 60" in pos and "[2015] SGHC 112" in pos:
            assert pos["[2022] SGCA 60"] < pos["[2015] SGHC 112"]
    # both scores retained for tuning
    assert all(hasattr(c, "ce_score") and hasattr(c, "authority_score")
               for c in r.chunks)


def _law_chunk(citation, tier, treatment="unknown", ce=0.9):
    from app.schemas import ChunkPayload, RetrievedChunk

    return RetrievedChunk(
        payload=ChunkPayload(chunk_id=citation, doc_id="d", text="t",
                             citation=citation, doc_type="judgment",
                             authority_tier=tier, treatment=treatment),
        ce_score=ce)


async def test_overruled_flagged_only_without_better_authority_above(ctx):
    from app.retrieval import coverage_check
    from app.schemas import FilteredCounts

    # overruled case on top, nothing better above → alarming
    low, reasons = coverage_check(ctx, [
        _law_chunk("[2015] SGHC 112", 5, "overruled"),
        _law_chunk("[2022] SGCA 60", 4),
    ], FilteredCounts())
    assert "overruled_authority_in_top_results" in reasons

    # binding authority already outranks the overruled case → resolved
    low, reasons = coverage_check(ctx, [
        _law_chunk("[2022] SGCA 60", 4),
        _law_chunk("[2015] SGHC 112", 5, "overruled"),
    ], FilteredCounts())
    assert "overruled_authority_in_top_results" not in reasons


async def test_scores_logged_in_debug(ctx):
    r = await retrieve(ctx, "part-time employee annual leave entitlement")
    assert r.debug.candidates_pre_rerank
    assert r.debug.timings_ms.get("total", 0) > 0

from app.ingest.citations import (
    edges_from_paragraphs,
    extract_neutral_citations,
    extract_statute_refs,
    resolve_treatment,
)


def test_extract_neutral_citations():
    text = ("As held in [2022] SGCA 60 and applied in [2019] SGHC(A) 3, "
            "see also [2022] SGCA 60 (again) and [2015] SGHC 112.")
    assert extract_neutral_citations(text) == [
        "[2022] SGCA 60", "[2019] SGHC(A) 3", "[2015] SGHC 112"]


def test_extract_statute_refs():
    text = ("A claim under s 14(2) of the Employment Act 1968 differs from one "
            "under section 13 of the Employment Claims Act 2016; see generally "
            "the Personal Data Protection Act 2012.")
    refs = extract_statute_refs(text)
    assert "Employment Act 1968, s 14(2)" in refs
    assert "Employment Claims Act 2016, s 13" in refs
    assert "Personal Data Protection Act 2012" in refs
    assert "Employment Act 1968" not in refs  # captured with its section already


def test_edge_hints_are_proximity_scoped():
    paras = [
        (1, "In our judgment, Ong v Rapid [2015] SGHC 112 was wrongly decided "
            "and is overruled. We say nothing about other cases."),
        (2, "The decision in Chua v Metro [2018] SGHC 44 is distinguishable."),
        (3, "We respectfully agree with the analysis in [2020] SGCA 1."),
    ]
    edges = edges_from_paragraphs("[2022] SGCA 60", paras)
    hints = {e.cited: e.treatment_hint for e in edges if e.kind == "case"}
    assert hints["[2015] SGHC 112"] == "overruled"
    assert hints["[2018] SGHC 44"] == "distinguished"
    assert hints["[2020] SGCA 1"] == "neutral"


def test_own_citation_excluded():
    edges = edges_from_paragraphs(
        "[2022] SGCA 60", [(1, "This is reported as [2022] SGCA 60.")])
    assert not [e for e in edges if e.kind == "case"]


def test_resolve_treatment_requires_higher_court():
    # a lower court cannot overrule a higher court's decision
    assert resolve_treatment([("overruled", 1, 5)]) != "overruled"
    assert resolve_treatment([("overruled", 5, 3)]) == "overruled"
    assert resolve_treatment([("distinguished", 3, 3)]) == "distinguished"
    assert resolve_treatment([("neutral", 3, 3)]) == "good"
    assert resolve_treatment([]) == "unknown"


async def test_treatment_pass_after_seed(ctx):
    overruled = await ctx.db.get_judgment("[2015] SGHC 112")
    assert overruled["treatment"] == "overruled"
    distinguished = await ctx.db.get_judgment("[2018] SGHC 44")
    assert distinguished["treatment"] == "distinguished"
    # the qdrant payloads carry the updated treatment too
    chunks = await ctx.store.by_doc_id("sg_law", overruled["doc_id"])
    assert chunks and all(c["treatment"] == "overruled" for c in chunks)


async def test_citation_graph_citing_endpoint_data(ctx):
    citing = await ctx.db.citing_of("[2015] SGHC 112")
    assert any(c["citation"] == "[2022] SGCA 60" for c in citing)
    citing_s14 = await ctx.db.citing_of("Employment Act 1968, s 14")
    assert any(c["citation"] == "[2022] SGCA 60" for c in citing_s14)

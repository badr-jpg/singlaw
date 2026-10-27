"""Editorial content: suggestion merging rules and discovery recall sanity."""
from app.content import POPULAR_LABEL, discoveries, merge_suggestions
from app.retrieval import retrieve


def _curated(n):
    return [{"label": f"L{i}", "text": f"Curated question {i}?"} for i in range(n)]


def test_merge_curated_first_then_popular():
    out = merge_suggestions(_curated(4), ["Real q A?", "Real q B?", "Real q C?"])
    assert len(out) == 4
    assert [o["label"] for o in out] == ["L0", "L1", POPULAR_LABEL, POPULAR_LABEL]
    assert [o["text"] for o in out[2:]] == ["Real q A?", "Real q B?"]


def test_merge_without_popular_is_all_curated():
    assert merge_suggestions(_curated(4), []) == _curated(4)
    assert len(merge_suggestions(_curated(6), [])) == 4


def test_merge_dedupes_popular_against_curated_case_insensitively():
    out = merge_suggestions(_curated(4), ["  curated QUESTION 1?  ", "Fresh?"])
    assert [o["text"] for o in out if o["label"] == POPULAR_LABEL] == ["Fresh?"]
    assert len(out) == 4


def test_merge_thin_curated_lets_more_popular_through():
    out = merge_suggestions(_curated(1), ["a?", "b?", "c?", "d?", "e?"])
    assert [o["text"] for o in out] == ["Curated question 0?", "a?", "b?", "c?"]
    out = merge_suggestions([], ["a?", "b?", "c?", "d?", "e?"])
    assert [o["text"] for o in out] == ["a?", "b?", "c?", "d?"]


async def test_discovery_questions_retrieve_their_cited_source(ctx):
    """Recall sanity: each discovery's `question` must surface the document it
    is grounded in (by manifest source_url) near the top of retrieval."""
    items = discoveries(ctx.settings.content_dir)
    assert len(items) == 5
    for item in items:
        result = await retrieve(ctx, item["question"])
        # chunk urls are deep links (…#pr14-); discoveries point at the document
        urls = [c.payload.source_url.split("#")[0] for c in result.chunks[:5]]
        assert item["url"] in urls, (item["id"], urls)

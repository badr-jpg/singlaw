from app.llm import ThinkTagFilter, parse_json_reply, strip_think


def feed_chunks(chunks):
    f = ThinkTagFilter()
    out = "".join(f.feed(c) for c in chunks)
    return out + f.flush()


def test_filter_passes_plain_text():
    assert feed_chunks(["Hello ", "world"]) == "Hello world"


def test_filter_strips_whole_block():
    assert feed_chunks(["<think>reasoning here</think>Answer"]) == "Answer"


def test_filter_strips_block_split_across_deltas():
    chunks = ["<th", "ink>step 1", " step 2</th", "ink>The answer", " is 42."]
    assert feed_chunks(chunks) == "The answer is 42."


def test_filter_handles_interleaved_thinking():
    chunks = ["Part one. <think>hmm</think>", "Part two.",
              "<think>more", " thought</think>", " Done."]
    assert feed_chunks(chunks) == "Part one. Part two. Done."


def test_filter_drops_unterminated_think():
    # completion truncated mid-thought: nothing after <think> may leak
    assert feed_chunks(["Answer.<think>ran out of tok"]) == "Answer."


def test_filter_holds_false_tag_prefix_then_releases():
    # "<th" could start a tag; once it turns out not to be one, it's emitted
    assert feed_chunks(["a <th", "ree-part test"]) == "a <three-part test"


def test_strip_think_non_streaming():
    assert strip_think("<think>x</think>ok") == "ok"
    assert strip_think("ok<think>truncated...") == "ok"
    assert strip_think("plain") == "plain"


def test_parse_json_after_think_strip():
    raw = '<think>{"decoy": 1} pondering</think>```json\n{"intent": "case_law"}\n```'
    assert parse_json_reply(strip_think(raw)) == {"intent": "case_law"}

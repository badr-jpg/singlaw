import json

from app.answer import chat_stream, detect_high_stakes, validate_grounding


def parse_sse(frames: list[str]) -> list[tuple[str, dict]]:
    events = []
    for frame in frames:
        ev, data = None, None
        for line in frame.strip().split("\n"):
            if line.startswith("event: "):
                ev = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((ev, data))
    return events


async def run_chat(ctx, message, doc_ids=None):
    frames = [f async for f in chat_stream(ctx, message, None, doc_ids)]
    return parse_sse(frames)


def by_event(events, name):
    return [d for e, d in events if e == name]


# ---------------- unit: validator + triggers ----------------

def test_validate_grounding_passes_cited_text():
    text = ("As at 2026-08-11, the following applies. An employer may dismiss "
            "an employee for misconduct only after due inquiry [CITE:1]. "
            "Wrongful dismissal claims go to the Employment Claims Tribunals [CITE:2].")
    v = validate_grounding(text, 3)
    assert v["grounded"] and not v["unsupported_sentences"] and not v["invalid_cites"]


def test_validate_grounding_flags_uncited_and_invalid():
    text = ("An employer may dismiss for misconduct after due inquiry [CITE:9]. "
            "Every employee is always entitled to three months of severance pay "
            "regardless of contract.")
    v = validate_grounding(text, 2)
    assert not v["grounded"]
    assert v["invalid_cites"] == [9]
    assert any("severance" in s for s in v["unsupported_sentences"])


def test_validate_grounding_cite_covers_preceding_claim_span():
    # legal-writing convention: several sentences, then the authority
    text = ("The words \"after due inquiry\" impose a mandatory procedural "
            "requirement on the employer. This means the inquiry must happen "
            "before the dismissal takes effect. A dismissal without due inquiry "
            "is wrongful even if misconduct is later proved [CITE:1].")
    v = validate_grounding(text, 2)
    assert v["grounded"], v
    # …but a trailing uncited claim after the last citation still flags
    text2 = text + (" Separately, every employee is always entitled to a "
                    "gratuity payment on dismissal regardless of contract.")
    v2 = validate_grounding(text2, 2)
    assert not v2["grounded"]
    assert any("gratuity" in s for s in v2["unsupported_sentences"])


def test_detect_high_stakes():
    assert detect_high_stakes("I was arrested and charged with theft")
    assert detect_high_stakes("my landlord served a notice to quit, am I being evicted?")
    assert detect_high_stakes("the limitation period for my claim expires soon")
    assert not detect_high_stakes("what is the minimum annual leave entitlement")


# ---------------- stream paths ----------------

async def test_drafting_refusal_stream(ctx):
    events = await run_chat(ctx, "Please draft a letter of demand to my landlord")
    meta = by_event(events, "meta")[0]
    assert meta["intent"] == "drafting_refused"
    tokens = "".join(d["text"] for d in by_event(events, "token"))
    assert "can't draft" in tokens
    assert by_event(events, "done")


async def test_high_stakes_referral_in_meta(ctx):
    events = await run_chat(ctx, "I was arrested — can my employer dismiss me for misconduct?")
    meta = by_event(events, "meta")[0]
    assert meta["high_stakes"]["triggered"]
    assert any("Legal Aid" in r["name"] for r in meta["high_stakes"]["referrals"])
    assert meta["disclaimer"]
    assert "Attorney-General" in meta["attribution"]


async def test_offline_extractive_answer_is_grounded(ctx):
    events = await run_chat(ctx, "can my employer dismiss me for misconduct without an inquiry")
    sources = by_event(events, "sources")[0]["sources"]
    assert sources, "expected retrieval to surface sources"
    text = "".join(d["text"] for d in by_event(events, "token"))
    assert "[CITE:" in text
    validation = by_event(events, "validation")[0]
    assert validation["grounded"]
    meta = by_event(events, "meta")[0]
    assert meta["temporal_basis"]  # answers state their temporal basis


async def test_conversation_persisted_with_sources(ctx):
    events = await run_chat(ctx, "what annual leave is a part-time employee entitled to")
    meta = by_event(events, "meta")[0]
    conv = await ctx.db.get_conversation(meta["conversation_id"])
    assert conv is not None
    roles = [m["role"] for m in conv["messages"]]
    assert roles[-2:] == ["user", "assistant"]
    assert conv["messages"][-1]["meta"]["attribution"]


class FakeProvider:
    """Streams a canned answer; complete() returns junk so analysis/rewrites
    fall back to heuristics."""

    name = "fake"
    configured = True

    def __init__(self, answer: str):
        self._answer = answer

    async def complete(self, messages, **kw):
        return "no json here"

    async def stream(self, messages, **kw):
        for i in range(0, len(self._answer), 20):
            yield self._answer[i:i + 20]


async def test_llm_path_validation_flags_ungrounded_claims(ctx):
    answer = ("As at 2026-08-11, an employer may dismiss an employee for "
              "misconduct only after due inquiry [CITE:1]. The employee is "
              "additionally always entitled to fourteen weeks of severance pay "
              "under the general law of contracts.")
    original = ctx.llm
    ctx.llm = FakeProvider(answer)
    try:
        events = await run_chat(ctx, "can my employer dismiss me for misconduct")
    finally:
        ctx.llm = original
    text = "".join(d["text"] for d in by_event(events, "token"))
    assert text == answer  # streamed verbatim
    validation = by_event(events, "validation")[0]
    assert not validation["grounded"]
    assert any("severance" in s for s in validation["unsupported_sentences"])

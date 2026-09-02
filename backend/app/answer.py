"""Grounded answer generation over SSE, with the legal-safety layer built in.

Protocol: the LLM cites sources as [CITE:n]; the `sources` SSE event maps n →
legal citation + URL, so the client renders real citations, never "[3]".
A post-stream grounding validator flags any material the sources don't back.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import date

from app.context import AppContext
from app.llm import LLMUnavailable
from app.retrieval import analyze_query, retrieve
from app.schemas import (
    AGC_ATTRIBUTION,
    LEGAL_INFO_DISCLAIMER,
    RetrievalResult,
    Source,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- safety

REFERRALS = [
    {"name": "Law Society Pro Bono Services", "url": "https://www.lawsocprobono.org"},
    {"name": "Legal Aid Bureau (MinLaw)", "url": "https://lab.mlaw.gov.sg"},
    {"name": "Criminal Legal Aid Scheme (CLAS)",
     "url": "https://www.lawsocprobono.org/clas"},
]

_HIGH_STAKES = [
    ("criminal matter", re.compile(
        r"\b(?:criminal charge|charged with|arrest(?:ed)?|police (?:report|investigation)"
        r"|prosecut|remand|bail|convict)", re.IGNORECASE)),
    ("immigration enforcement", re.compile(
        r"\b(?:deport|removal order|immigration (?:offence|detention)|overstay"
        r"|work pass (?:cancell|revok))", re.IGNORECASE)),
    ("court deadline or limitation period", re.compile(
        r"\b(?:deadline|time limit|limitation period|time[- ]bar|within \d+ (?:days|weeks|months)"
        r"|miss(?:ed)? the (?:filing|deadline)|court (?:date|hearing) (?:tomorrow|next week))", re.IGNORECASE)),
    ("eviction or loss of home", re.compile(
        r"\b(?:evict|notice to quit|repossess|writ of possession)", re.IGNORECASE)),
]


def detect_high_stakes(text: str) -> list[str]:
    return [reason for reason, rx in _HIGH_STAKES if rx.search(text)]


# ---------------------------------------------------------------- prompts

_SYSTEM_PROMPT = """You are a legal information assistant for Singapore law. You explain what the law says; you never give legal advice or tell the user what to do in their specific dispute.

STRICT GROUNDING RULES — these override everything else:
1. Use ONLY the numbered sources provided. You have no other knowledge. If the sources do not answer the question, say exactly that and suggest where the user might look (Singapore Statutes Online, a lawyer) — never fill gaps from memory.
2. Every factual or legal proposition MUST end with a citation marker like [CITE:1] referring to the source that supports it. A sentence you cannot cite must not be written. This includes restatements ("in other words …") and sentences that name a case or provision in prose — writing a case name or neutral citation as text is NOT a citation; only the [CITE:n] marker counts, so add it even when the sentence already names the authority.
3. Sources from the user's own documents (marked USER DOCUMENT) describe the user's factual situation. They are never legal authority — use them only to explain which law is relevant.
4. Respect authority: Constitution > Act > subsidiary legislation > binding judgment (Court of Appeal / Appellate Division) > other courts > guidance. If two sources conflict, say which prevails and why, citing both.
5. If a source is marked REPEALED or OVERRULED, you may mention it only with that warning stated in the same sentence.
6. Begin the substantive answer by stating its temporal basis: "As at {as_at}, ...".
7. Frame everything as legal information. Do not recommend a course of action in the user's dispute. Explaining options in the abstract is fine.
8. Never draft or dictate text intended to be filed in court or served on another party.
9. Write plain, precise English a layperson can follow. Define statutory terms when you use them.
10. Do not append advice, disclaimers, or "consult a lawyer" closings — the interface already displays the legal-information disclaimer and referral guidance around your answer."""

_LOW_CONFIDENCE_ADDENDUM = """
RETRIEVAL CONFIDENCE IS LOW ({reasons}). Open your answer by telling the user plainly that you could not find strong authority for this question, answer only what the sources genuinely support, and keep the rest brief."""


def _source_block(sources: list[Source], texts: dict[int, tuple[str, str]]) -> str:
    lines = []
    for s in sources:
        flags = []
        if s.status not in ("in_force", "n_a"):
            flags.append(s.status.upper())
        if s.treatment == "overruled":
            flags.append("OVERRULED")
        if s.collection == "user_docs":
            flags.append("USER DOCUMENT")
        flag = f" [{', '.join(flags)}]" if flags else ""
        context, text = texts[s.n]
        lines.append(f"[Source {s.n}] {s.citation}{flag}\n{context}\n{text}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------- validation

_SENT_SPLIT_RX = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_CITE_RX = re.compile(r"\[CITE:(\d+)\]")
_BOILERPLATE_RX = re.compile(
    r"^(?:as at\b|in summary\b|note:|this is (?:general )?legal information"
    r"|i could not find|the sources (?:provided )?do not|for advice\b"
    r"|if (?:you|this) (?:need|is urgent)|you may wish to consult|see also\b"
    r"|#|\*|-|\d+\.)", re.IGNORECASE)


def validate_grounding(text: str, n_sources: int) -> dict:
    """Every factual proposition needs a valid [CITE:n]. Flag what doesn't.

    Coverage follows legal writing convention: a valid citation covers its own
    sentence and any uncited sentences before it in the same paragraph (a
    claim-span ending in its authority). Trailing uncited claims still flag.
    """
    invalid = sorted({int(n) for n in _CITE_RX.findall(text) if int(n) > n_sources or int(n) < 1})

    def has_valid_cite(s: str) -> bool:
        return any(1 <= int(n) <= n_sources for n in _CITE_RX.findall(s))

    unsupported: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if re.match(r"^(?:[-*#•]|\d+\.)\s", para):
            # a bullet/heading is one unit: a trailing citation covers it
            if len(para) >= 40 and not has_valid_cite(para) and not para.startswith("#"):
                unsupported.append(para[:200])
            continue
        pending: list[str] = []  # uncited claims awaiting a covering citation
        for sent in _SENT_SPLIT_RX.split(para):
            sent = sent.strip()
            if has_valid_cite(sent):
                pending.clear()  # the cite covers the claim-span before it
                continue
            if (len(sent) < 40 or _BOILERPLATE_RX.match(sent)
                    or sent.endswith(":")):  # lead-in to a cited list/quote
                continue
            pending.append(sent[:200])
        unsupported.extend(pending)
    return {"grounded": not invalid and not unsupported,
            "unsupported_sentences": unsupported[:10], "invalid_cites": invalid}


# ---------------------------------------------------------------- sources

def to_sources(result: RetrievalResult) -> tuple[list[Source], dict[int, tuple[str, str]]]:
    sources, texts = [], {}
    for i, rc in enumerate(result.chunks, start=1):
        p = rc.payload
        sources.append(Source(
            n=i, chunk_id=p.chunk_id, citation=p.citation, url=p.source_url,
            doc_type=p.doc_type, authority_tier=p.authority_tier, status=p.status,
            treatment=p.treatment, court=p.court,
            decision_date=p.decision_date.isoformat() if p.decision_date else None,
            hierarchy_path=p.hierarchy_path, snippet=p.text[:240],
            collection=p.collection))
        texts[i] = (p.context, p.text[:2500])
    return sources, texts


# ---------------------------------------------------------------- canned paths

_DRAFTING_REFUSAL = (
    "I can't draft documents intended to be filed in court or served on another "
    "party — a letter of demand, pleading, affidavit or similar needs to come "
    "from you or a lawyer acting for you. What I can do is explain the law that "
    "applies to your situation so you understand your position. If you tell me "
    "what the dispute is about, I'll find the relevant provisions."
)

_OUT_OF_SCOPE_TEMPLATE = (
    "This assistant covers Singapore law only, and this question appears to be "
    "outside that scope{reason}. For Singapore legislation, see Singapore "
    "Statutes Online (https://sso.agc.gov.sg); for Singapore judgments, "
    "https://www.judiciary.gov.sg. For other jurisdictions you will need a "
    "source or adviser for that jurisdiction."
)

_EMPTY_RESULT_TEXT = (
    "I could not find anything in the corpus that answers this with real "
    "authority, so I won't guess — a confident answer without a source would be "
    "worse than none. You could try rephrasing with more specific terms, browse "
    "the corpus in the Explorer, or check Singapore Statutes Online "
    "(https://sso.agc.gov.sg) directly."
)


def _extractive_fallback(sources: list[Source], as_at: str) -> str:
    """No LLM configured: a citations-only extractive answer, trivially grounded."""
    law = [s for s in sources if s.collection == "sg_law"][:5]
    if not law:
        return _EMPTY_RESULT_TEXT
    lines = [f"As at {as_at}, these are the most relevant authorities I found "
             "(no generation model is configured, so I'm listing them rather "
             "than writing a narrative answer):", ""]
    for s in law:
        snippet = " ".join(s.snippet.split())[:220]
        lines.append(f"- {s.citation} [CITE:{s.n}] — {snippet}…")
    lines += ["", "Open each citation for the full text."]
    return "\n".join(lines)


# ---------------------------------------------------------------- the stream

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def chat_stream(
    ctx: AppContext, message: str, conversation_id: str | None,
    doc_ids: list[str] | None,
) -> AsyncIterator[str]:
    """The full /api/chat pipeline as an SSE stream."""
    try:
        async for frame in _chat_stream_inner(ctx, message, conversation_id, doc_ids):
            yield frame
    except Exception:
        log.exception("chat stream failed")
        yield sse("error", {"message": "Something went wrong while answering. "
                                       "Your message was saved; please retry."})


async def _chat_stream_inner(
    ctx: AppContext, message: str, conversation_id: str | None,
    doc_ids: list[str] | None,
) -> AsyncIterator[str]:
    db = ctx.db
    if conversation_id is None or not await db.get_conversation(conversation_id):
        conversation_id = await db.create_conversation(
            title=(message[:57] + "…") if len(message) > 58 else message)
    await db.add_message(conversation_id, "user", message)

    analysis = await analyze_query(ctx, message)
    as_at = (analysis.temporal_anchor or date.today()).isoformat()
    high_stakes = detect_high_stakes(message)
    last_sync = await db.kv_get("last_sync") or await db.kv_get("last_seed")

    def meta_event(intent: str, result: RetrievalResult | None) -> dict:
        return {
            "conversation_id": conversation_id, "message_id": "",
            "intent": intent,
            "low_confidence": bool(result and result.low_confidence),
            "low_confidence_reasons": result.low_confidence_reasons if result else [],
            "filtered": (result.filtered.model_dump() if result
                         else {"repealed": 0, "spent": 0, "not_yet_commenced": 0}),
            "temporal_basis": as_at,
            "high_stakes": {"triggered": bool(high_stakes), "reasons": high_stakes,
                            "referrals": REFERRALS if high_stakes else []},
            "attribution": AGC_ATTRIBUTION, "disclaimer": LEGAL_INFO_DISCLAIMER,
            "corpus_last_synced": last_sync,
        }

    async def finish(intent: str, text: str, sources: list[Source],
                     result: RetrievalResult | None, validation: dict) -> AsyncIterator[str]:
        meta = meta_event(intent, result)
        meta["validation"] = validation
        mid = await db.add_message(conversation_id, "assistant", text,
                                   sources=[s.model_dump() for s in sources], meta=meta)
        yield sse("validation", validation)
        yield sse("done", {"message_id": mid, "finish_reason": "stop"})

    # -- refusal / out-of-scope short paths ------------------------------
    if analysis.wants_drafting:
        yield sse("meta", meta_event("drafting_refused", None))
        yield sse("sources", {"sources": []})
        yield sse("token", {"text": _DRAFTING_REFUSAL})
        async for f in finish("drafting_refused", _DRAFTING_REFUSAL, [], None,
                              {"grounded": True, "unsupported_sentences": [],
                               "invalid_cites": []}):
            yield f
        return
    if analysis.out_of_scope:
        reason = f" ({analysis.out_of_scope_reason.rstrip('.')})" \
            if analysis.out_of_scope_reason else ""
        text = _OUT_OF_SCOPE_TEMPLATE.format(reason=reason)
        yield sse("meta", meta_event("out_of_scope", None))
        yield sse("sources", {"sources": []})
        yield sse("token", {"text": text})
        async for f in finish("out_of_scope", text, [], None,
                              {"grounded": True, "unsupported_sentences": [],
                               "invalid_cites": []}):
            yield f
        return

    # -- retrieval -------------------------------------------------------
    result = await retrieve(ctx, message, doc_ids=doc_ids, analysis=analysis)
    sources, texts = to_sources(result)
    yield sse("meta", meta_event(analysis.intent, result))
    yield sse("sources", {"sources": [s.model_dump() for s in sources]})

    # -- generation ------------------------------------------------------
    if not sources:
        text = _EMPTY_RESULT_TEXT
        yield sse("token", {"text": text})
        async for f in finish(analysis.intent, text, sources, result,
                              validate_grounding(text, 0)):
            yield f
        return

    if not ctx.llm.configured:
        text = _extractive_fallback(sources, as_at)
        yield sse("token", {"text": text})
        async for f in finish(analysis.intent, text, sources, result,
                              validate_grounding(text, len(sources))):
            yield f
        return

    system = _SYSTEM_PROMPT.format(as_at=as_at)
    if result.low_confidence:
        system += _LOW_CONFIDENCE_ADDENDUM.format(
            reasons=", ".join(result.low_confidence_reasons))
    history = await db.message_history(conversation_id, limit=8)
    msgs = ([{"role": "system", "content": system}]
            + history[:-1]
            + [{"role": "user", "content":
                f"SOURCES:\n\n{_source_block(sources, texts)}\n\n"
                f"QUESTION: {message}"}])

    full: list[str] = []
    try:
        async for delta in ctx.llm.stream(msgs, max_tokens=8000):
            full.append(delta)
            yield sse("token", {"text": delta})
    except LLMUnavailable:
        text = _extractive_fallback(sources, as_at)
        yield sse("token", {"text": text})
        full = [text]
    except Exception as exc:
        log.exception("generation failed")
        yield sse("error", {"message": f"The generation service failed ({exc}). "
                                       "Retrieved sources are shown above."})
        full.append("")
    text = "".join(full)
    async for f in finish(analysis.intent, text, sources, result,
                          validate_grounding(text, len(sources))):
        yield f

"""Shared data models: chunk metadata (spec §2.4), API shapes, SSE payloads."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

DocType = Literal[
    "act",
    "subsidiary_legislation",
    "judgment",
    "practice_direction",
    # phase-2 sources are representable now, not ingested yet
    "guidance",
    "user_document",
]
Status = Literal["in_force", "repealed", "spent", "not_yet_commenced", "n_a"]
Treatment = Literal["good", "distinguished", "overruled", "unknown"]
Intent = Literal[
    "statutory_lookup",
    "procedural",
    "rights_obligations",
    "case_law",
    "out_of_scope",
    "drafting_refused",
]

# authority_tier: 1=Constitution, 2=Act, 3=SL, 4=binding judgment,
# 5=lower court, 6=guidance/non-binding
TIER_CONSTITUTION = 1
TIER_ACT = 2
TIER_SL = 3
TIER_BINDING_JUDGMENT = 4
TIER_LOWER_COURT = 5
TIER_GUIDANCE = 6

# court_level: higher number = higher court (used for treatment pass)
COURT_LEVELS: dict[str, int] = {
    "SGCA": 5,   # Court of Appeal
    "SGCA(I)": 5,  # Court of Appeal, international commercial
    "SGHC(A)": 4,  # Appellate Division
    "SGHC": 3,   # General Division
    "SGHC(I)": 3,  # SICC
    "SGHCF": 3,
    "SGHCR": 2,  # Registrar
    "SGDC": 1,
    "SGMC": 1,
}
BINDING_COURTS = {"SGCA", "SGCA(I)", "SGHC(A)"}

AGC_ATTRIBUTION = (
    "Legislation reproduced here is © Singapore Government and reproduced with "
    "the permission of the Attorney-General's Chambers under the Singapore "
    "Statutes Online terms of use. Check https://sso.agc.gov.sg for the latest "
    "version. Material downloaded from SSO is not an authoritative text: "
    "section 48 of the Interpretation Act 1965 does not apply to it — the "
    "Gazette remains the authoritative text."
)
LEGAL_INFO_DISCLAIMER = (
    "This assistant provides legal information, not legal advice. It explains "
    "what the law says; it cannot tell you what to do in your specific "
    "situation. For advice on your own matter, consult a lawyer."
)


class ChunkPayload(BaseModel):
    """Payload stored on every Qdrant point. Spec §2.4 plus storage fields."""

    # storage / identity
    chunk_id: str
    doc_id: str
    collection: Literal["sg_law", "user_docs"] = "sg_law"
    user_id: str | None = None  # user_docs only
    text: str
    context: str = ""  # contextual-retrieval prefix (structural or LLM-derived)
    title: str = ""    # document title (Act name / case name / filename)

    # spec §2.4 — non-negotiable
    doc_type: DocType
    authority_tier: int = TIER_GUIDANCE
    status: Status = "in_force"
    in_force_from: date | None = None
    in_force_to: date | None = None
    repealed_by: str | None = None
    citation: str = ""
    hierarchy_path: list[str] = Field(default_factory=list)
    court: str | None = None
    court_level: int | None = None
    decision_date: date | None = None
    cites: list[str] = Field(default_factory=list)
    treatment: Treatment = "unknown"
    source_url: str = ""
    sso_version_date: date | None = None

    def qdrant_payload(self) -> dict[str, Any]:
        """JSON-safe payload with int date mirrors for portable range filters."""
        p = self.model_dump(mode="json")
        for f in ("decision_date", "in_force_from", "in_force_to"):
            v = getattr(self, f)
            p[f + "_int"] = int(v.strftime("%Y%m%d")) if v else None
        return p


class Source(BaseModel):
    """A retrieved chunk as surfaced to the client."""

    n: int
    chunk_id: str
    citation: str
    url: str
    doc_type: str
    authority_tier: int
    status: str
    treatment: str
    court: str | None = None
    decision_date: str | None = None
    hierarchy_path: list[str] = Field(default_factory=list)
    snippet: str = ""
    collection: str = "sg_law"


class QueryAnalysis(BaseModel):
    intent: Intent = "rights_obligations"
    citations: list[str] = Field(default_factory=list)
    temporal_anchor: date | None = None  # "what was the law in 2019?"
    include_repealed: bool = False
    out_of_scope: bool = False
    out_of_scope_reason: str = ""
    wants_drafting: bool = False


class RetrievedChunk(BaseModel):
    payload: ChunkPayload
    rrf_score: float = 0.0
    ce_score: float = 0.0
    ce_norm: float = 0.0
    authority_score: float = 0.0
    recency_score: float = 0.0
    final_score: float = 0.0
    pinned: bool = False  # citation short-circuit → rank 0


class FilteredCounts(BaseModel):
    repealed: int = 0
    spent: int = 0
    not_yet_commenced: int = 0

    @property
    def total(self) -> int:
        return self.repealed + self.spent + self.not_yet_commenced


class RetrievalDebug(BaseModel):
    rewrites: list[str] = Field(default_factory=list)
    hyde: str | None = None
    citation_shortcircuit: list[str] = Field(default_factory=list)
    candidates_pre_filter: int = 0
    candidates_pre_rerank: list[dict[str, Any]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    analysis: QueryAnalysis = Field(default_factory=QueryAnalysis)
    filtered: FilteredCounts = Field(default_factory=FilteredCounts)
    low_confidence: bool = False
    low_confidence_reasons: list[str] = Field(default_factory=list)
    debug: RetrievalDebug = Field(default_factory=RetrievalDebug)


# ---- API request/response ----

class ChatRequest(BaseModel):
    message: str = ""  # may be blank when regenerate=True (it is ignored then)
    conversation_id: str | None = None
    doc_ids: list[str] | None = None
    business_id: str | None = None  # v2: scope to a business workspace
    regenerate: bool = False        # v2: re-answer the last user turn


class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    include_debug: bool = False
    doc_ids: list[str] | None = None
    business_id: str | None = None


class RenameRequest(BaseModel):
    title: str


class SyncRequest(BaseModel):
    force: bool = False


# ---- v2 (SingLaw UI addendum, 2026-10-07) ----

class CreateConversationRequest(BaseModel):
    title: str | None = None


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    icon: str = Field(default="Building2", max_length=40)


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=40)


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=2000)


class CheckoutRequest(BaseModel):
    plan_id: str
    interval: Literal["monthly", "yearly"] = "monthly"


_EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class WaitlistRequest(BaseModel):
    email: str = Field(max_length=254)
    plan_id: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RX.match(v):
            raise ValueError("invalid email address")
        return v.lower()

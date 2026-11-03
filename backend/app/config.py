"""Application settings. Everything tunable lives here; env vars override."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

_PROFILES: dict[str, dict[str, str]] = {
    "full": {
        "embedding": "Qwen/Qwen3-Embedding-0.6B",
        "reranker": "jinaai/jina-reranker-v2-base-multilingual",
    },
    "dev": {
        "embedding": "sentence-transformers/all-MiniLM-L6-v2",
        "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    },
    # stub: deterministic hash embeddings + lexical reranker, no downloads.
    "stub": {"embedding": "stub", "reranker": "stub"},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- paths ---
    data_dir: Path = ROOT / "data"
    archive_dir: Path = ROOT / "data" / "archive"

    # --- models ---
    model_profile: Literal["full", "dev", "stub"] = "full"
    embedding_model: str | None = None
    reranker_model: str | None = None

    # --- LLM (generation / rewriting / HyDE only) ---
    minimax_api_key: str = ""
    llm_base_url: str = "https://api.minimax.io/v1"
    llm_model: str = "MiniMax-M3"  # verified against /v1/models 2026-11-03 (M2.7 being retired)
    # analysis / rewriting / HyDE / document-context calls: a faster variant than the
    # answer model (a non-reasoning Flash model). Falls back to llm_model.
    llm_fast_model: str = "MiniMax-M3.1-Flash"
    # total wall-clock budget for the pre-retrieval LLM calls (analysis, rewrites,
    # HyDE), measured from question arrival. Past it, analysis falls back to the
    # instant heuristics and whatever enrichment has arrived is used; the late
    # calls still finish in the background to warm the per-question cache.
    llm_prestage_budget_seconds: float = 15.0
    llm_timeout_seconds: float = 120.0

    # --- SSO crawler ---
    crawl_window_start: str = "05:00"  # Asia/Singapore, per SSO terms of use
    crawl_window_end: str = "07:00"
    crawl_tz: str = "Asia/Singapore"
    crawl_delay_seconds: float = 2.0
    crawl_max_backoff_seconds: float = 300.0
    sso_base_url: str = "https://sso.agc.gov.sg"
    sso_whats_new_path: str = "/Browse/Whats-New"
    judiciary_base_url: str = "https://www.judiciary.gov.sg"

    # --- retrieval ---
    top_k_per_list: int = 75          # dense and sparse, per query variant
    rrf_k: int = 60
    fusion_top: int = 150
    rerank_top: int = 30
    final_top: int = 20
    n_rewrites: int = 3
    user_docs_top_k: int = 10

    # authority-aware final rank: final = w_ce*ce_norm + w_auth*tier + w_rec*recency
    w_cross_encoder: float = 0.6
    w_authority: float = 0.25
    w_recency: float = 0.15
    low_confidence_threshold: float = 0.25

    # --- storage ---
    user_id: str = "local"  # single local user in v1; schema is multi-user ready

    # --- workspaces / editorial content ---
    max_businesses: int = 0  # operator ceiling on workspaces; 0 = follow the active plan
    content_dir: Path = ROOT / "data" / "content"  # suggestions.json / discoveries.json

    # --- billing (optional; unset → /api/billing/checkout answers 503, UI offers waitlist) ---
    stripe_secret_key: str = ""
    stripe_price_ids: str = ""  # JSON: {"business:monthly": "price_…", "business:yearly": "price_…"}
    stripe_webhook_secret: str = ""  # whsec_…; when set, /api/billing/webhook verifies signatures
    public_base_url: str = "http://localhost:8000"  # Checkout success/cancel redirect origin

    @property
    def qdrant_path(self) -> Path:
        return self.data_dir / "qdrant"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "app.sqlite3"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def embedding_model_resolved(self) -> str:
        return self.embedding_model or _PROFILES[self.model_profile]["embedding"]

    @property
    def reranker_model_resolved(self) -> str:
        return self.reranker_model or _PROFILES[self.model_profile]["reranker"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

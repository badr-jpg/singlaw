"""Local model layer: dense embedder, cross-encoder reranker, BM25 sparse encoder.

Everything here runs in-process with no network calls at inference time.
Models load once into a shared ModelRegistry singleton at startup (spec Part 5).

Profiles (config.MODEL_PROFILE):
  full — Qwen3-Embedding-0.6B + jina-reranker-v2 (spec defaults)
  dev  — small fast models for local iteration
  stub — deterministic hash embeddings + lexical reranker; zero downloads,
         used by the offline test suite
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path

import numpy as np

from app.config import Settings

log = logging.getLogger(__name__)

SparseVector = tuple[list[int], list[float]]  # (indices, values)


def _local_first(loader):
    """Load a HF model from the local cache without any network round-trips;
    fall back to a downloading load only when the cache misses.

    Without this, sentence-transformers revalidates every cached file against
    the Hub on load — unauthenticated requests get rate-limited and the
    startup stalls for minutes on a warm cache.
    """
    import os

    if os.environ.get("HF_HUB_OFFLINE") == "1":
        return loader()
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        return loader()
    except Exception:
        os.environ.pop("HF_HUB_OFFLINE", None)
        return loader()
    finally:
        os.environ.pop("HF_HUB_OFFLINE", None)


# ------------------------------------------------------------------ sparse

class SparseEncoder:
    """BM25 term-impact encoder for Qdrant named sparse vectors.

    Doc side stores the TF component; Qdrant's `Modifier.IDF` applies IDF at
    query time from live corpus stats, so earlier points stay consistent as
    the corpus grows. Token ids are stable 32-bit hashes — no vocab store.
    """

    k1 = 1.5
    b = 0.75

    def __init__(self, stats_path: Path):
        self._stats_path = stats_path
        self._stats: dict[str, dict[str, float]] = {}
        if stats_path.exists():
            self._stats = json.loads(stats_path.read_text())

    @staticmethod
    def _tokenize(texts: list[str]) -> list[list[str]]:
        import bm25s

        return bm25s.tokenize(texts, stopwords="english", return_ids=False,
                              show_progress=False)

    @staticmethod
    def _hash(token: str) -> int:
        return int.from_bytes(
            hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest(), "little"
        )

    def _avgdl(self, collection: str) -> float:
        s = self._stats.get(collection, {})
        return (s.get("total_len", 0.0) / s["n_docs"]) if s.get("n_docs") else 1.0

    def encode_docs(self, texts: list[str], collection: str) -> list[SparseVector]:
        token_lists = self._tokenize(texts)
        s = self._stats.setdefault(collection, {"n_docs": 0, "total_len": 0.0})
        s["n_docs"] += len(token_lists)
        s["total_len"] += float(sum(len(t) for t in token_lists))
        self._stats_path.parent.mkdir(parents=True, exist_ok=True)
        self._stats_path.write_text(json.dumps(self._stats))

        avgdl = self._avgdl(collection)
        out: list[SparseVector] = []
        for tokens in token_lists:
            dl = len(tokens) or 1
            norm = self.k1 * (1 - self.b + self.b * dl / avgdl)
            weights: dict[int, float] = {}
            for tok, tf in Counter(tokens).items():
                weights[self._hash(tok)] = tf * (self.k1 + 1) / (tf + norm)
            out.append((list(weights.keys()), list(weights.values())))
        return out

    def encode_query(self, text: str) -> SparseVector:
        tokens = self._tokenize([text])[0]
        idx = sorted({self._hash(t) for t in tokens})
        return idx, [1.0] * len(idx)


# ------------------------------------------------------------------ dense

class StubEmbedder:
    """Deterministic bag-of-hashed-tokens embedding. Offline tests only."""

    dim = 256

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            v[int.from_bytes(h[:4], "little") % self.dim] += 1.0
            v[int.from_bytes(h[4:], "little") % self.dim] += 0.5
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts])

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self.encode_docs(texts)


class STEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = _local_first(
            lambda: SentenceTransformer(model_name, trust_remote_code=True))
        self.dim = int(self.model.get_sentence_embedding_dimension())
        log.info("embedder %s on %s (%d-dim)", model_name, self.model.device, self.dim)
        # Qwen3-Embedding ships an asymmetric "query" prompt in its config
        self._query_prompt = "query" if "query" in (self.model.prompts or {}) else None

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True,
                                 show_progress_bar=False)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        kw = {"prompt_name": self._query_prompt} if self._query_prompt else {}
        return self.model.encode(texts, normalize_embeddings=True,
                                 show_progress_bar=False, **kw)


# ------------------------------------------------------------------ rerank

class StubReranker:
    """Token-overlap scorer standing in for a cross-encoder in tests."""

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = self._tokens(query)
        out = []
        for t in texts:
            d = self._tokens(t)
            out.append(len(q & d) / len(q | d) if q | d else 0.0)
        return out


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self.model = _local_first(
            lambda: CrossEncoder(model_name, trust_remote_code=True))

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        scores = self.model.predict([(query, t) for t in texts],
                                    show_progress_bar=False)
        return [float(s) for s in scores]


class QwenReranker:
    """Qwen3-Reranker-* is a causal LM scored on its yes/no logits."""

    _PREFIX = (
        "<|im_start|>system\nJudge whether the Document meets the requirements "
        "based on the Query and the Instruct provided. Note that the answer can "
        'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
    )
    _SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    _INSTRUCT = "Given a legal research query, retrieve provisions and judgments that answer it"

    def __init__(self, model_name: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        self._device = ("cuda" if torch.cuda.is_available()
                        else "mps" if torch.backends.mps.is_available() else "cpu")
        self.tokenizer = _local_first(
            lambda: AutoTokenizer.from_pretrained(model_name, padding_side="left"))
        self.model = _local_first(
            lambda: AutoModelForCausalLM.from_pretrained(model_name)
        ).eval().to(self._device)
        self._yes = self.tokenizer.convert_tokens_to_ids("yes")
        self._no = self.tokenizer.convert_tokens_to_ids("no")

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        torch = self._torch
        pairs = [
            f"{self._PREFIX}<Instruct>: {self._INSTRUCT}\n<Query>: {query}\n"
            f"<Document>: {t}{self._SUFFIX}"
            for t in texts
        ]
        out: list[float] = []
        with torch.no_grad():
            for i in range(0, len(pairs), 8):
                batch = self.tokenizer(pairs[i:i + 8], return_tensors="pt",
                                       padding=True, truncation=True, max_length=4096
                                       ).to(self._device)
                logits = self.model(**batch).logits[:, -1, :]
                pair_logits = torch.stack([logits[:, self._no], logits[:, self._yes]], dim=1)
                out.extend(torch.nn.functional.log_softmax(pair_logits, dim=1)[:, 1]
                           .exp().tolist())
        return out


# ------------------------------------------------------------------ registry

class ModelRegistry:
    """Shared singleton; loaded once at startup, never per-request."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self.loaded = False
        self.embedder: StubEmbedder | STEmbedder | None = None
        self.reranker = None
        self.reranker_name_active: str | None = None
        self.sparse: SparseEncoder | None = None

    @property
    def embedding_model_name(self) -> str:
        return self._settings.embedding_model_resolved

    @property
    def reranker_model_name(self) -> str:
        return self._settings.reranker_model_resolved

    def _load_sync(self) -> None:
        s = self._settings
        self.sparse = SparseEncoder(s.cache_dir / "bm25_stats.json")
        if s.embedding_model_resolved == "stub":
            self.embedder = StubEmbedder()
        else:
            self.embedder = STEmbedder(s.embedding_model_resolved)
        rname = s.reranker_model_resolved
        if rname == "stub":
            self.reranker = StubReranker()
        elif "Qwen3-Reranker" in rname:
            self.reranker = QwenReranker(rname)
        else:
            try:
                self.reranker = CrossEncoderReranker(rname)
            except ImportError as exc:
                # jina-reranker-v2's trust_remote_code targets an older
                # transformers API; the Qwen3 embedder needs a modern one.
                # Fall back to the spec's sanctioned alternative reranker.
                fallback = "Qwen/Qwen3-Reranker-0.6B"
                log.warning(
                    "reranker %s is incompatible with the installed "
                    "transformers (%s) — falling back to %s. Set "
                    "RERANKER_MODEL to silence this.", rname, exc, fallback)
                self.reranker = QwenReranker(fallback)
                rname = fallback
        self.reranker_name_active = rname
        self.loaded = True

    async def load(self) -> None:
        if not self.loaded:
            await asyncio.to_thread(self._load_sync)

    # async conveniences (model inference is blocking → thread pool)
    async def embed_docs(self, texts: list[str]) -> np.ndarray:
        return await asyncio.to_thread(self.embedder.encode_docs, texts)

    async def embed_queries(self, texts: list[str]) -> np.ndarray:
        return await asyncio.to_thread(self.embedder.encode_queries, texts)

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        return await asyncio.to_thread(self.reranker.score, query, texts)



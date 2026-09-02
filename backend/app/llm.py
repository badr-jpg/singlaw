"""LLM provider interface. MiniMax (OpenAI-compatible) is the default; a
local vLLM endpoint is a base-URL swap away — call sites never change.

The LLM is used ONLY for: answer generation, query rewriting/analysis, HyDE,
and user-document context. Retrieval works fully offline without it.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Protocol

from app.config import Settings


class LLMUnavailable(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    configured: bool

    async def complete(self, messages: list[dict[str, str]], *,
                       max_tokens: int = 1024, temperature: float = 0.2) -> str: ...

    def stream(self, messages: list[dict[str, str]], *,
               max_tokens: int = 2048, temperature: float = 0.2,
               ) -> AsyncIterator[str]: ...


class ThinkTagFilter:
    """Strips <think>…</think> blocks from a token stream.

    MiniMax M-series (and other reasoning models served over OpenAI-compatible
    APIs) interleave chain-of-thought inline in the content. It must never
    reach the user as answer text, and tags can be split across deltas, so the
    filter is stateful and holds back any suffix that might start a tag.
    """

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._thinking = False

    @staticmethod
    def _held_tail(s: str, tag: str) -> int:
        for k in range(min(len(tag) - 1, len(s)), 0, -1):
            if tag.startswith(s[-k:]):
                return k
        return 0

    def feed(self, delta: str) -> str:
        self._buf += delta
        out: list[str] = []
        while True:
            if self._thinking:
                idx = self._buf.find(self.CLOSE)
                if idx == -1:
                    self._buf = self._buf[-(len(self.CLOSE) - 1):]
                    break
                self._buf = self._buf[idx + len(self.CLOSE):]
                self._thinking = False
                continue
            idx = self._buf.find(self.OPEN)
            if idx == -1:
                held = self._held_tail(self._buf, self.OPEN)
                emit = self._buf[: len(self._buf) - held]
                self._buf = self._buf[len(self._buf) - held:] if held else ""
                if emit:
                    out.append(emit)
                break
            out.append(self._buf[:idx])
            self._buf = self._buf[idx + len(self.OPEN):]
            self._thinking = True
        return "".join(out)

    def flush(self) -> str:
        tail = "" if self._thinking else self._buf
        self._buf, self._thinking = "", False
        return tail


_THINK_BLOCK_RX = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_UNTERMINATED_RX = re.compile(r"<think>.*\Z", re.DOTALL)


def strip_think(text: str) -> str:
    """Non-streaming variant: drop closed blocks, and anything after an
    unterminated <think> (the completion ran out of tokens mid-thought)."""
    return _THINK_UNTERMINATED_RX.sub("", _THINK_BLOCK_RX.sub("", text)).strip()


class OpenAICompatProvider:
    """Works for MiniMax's OpenAI-compatible API and for local vLLM."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float):
        from openai import AsyncOpenAI

        self.name = f"{model} @ {base_url}"
        self.model = model
        self.configured = bool(api_key)
        self._client = AsyncOpenAI(api_key=api_key or "unset", base_url=base_url,
                                   timeout=timeout)

    async def complete(self, messages, *, max_tokens=1024, temperature=0.2) -> str:
        if not self.configured:
            raise LLMUnavailable("No LLM API key configured")
        resp = await self._client.chat.completions.create(
            model=self.model, messages=messages,
            max_tokens=max_tokens, temperature=temperature)
        return strip_think(resp.choices[0].message.content or "")

    async def stream(self, messages, *, max_tokens=2048, temperature=0.2):
        if not self.configured:
            raise LLMUnavailable("No LLM API key configured")
        stream = await self._client.chat.completions.create(
            model=self.model, messages=messages,
            max_tokens=max_tokens, temperature=temperature, stream=True)
        filt = ThinkTagFilter()
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                out = filt.feed(chunk.choices[0].delta.content)
                if out:
                    yield out
        tail = filt.flush()
        if tail:
            yield tail


class NullProvider:
    name = "none"
    configured = False

    async def complete(self, messages, *, max_tokens=1024, temperature=0.2) -> str:
        raise LLMUnavailable("No LLM configured")

    async def stream(self, messages, *, max_tokens=2048, temperature=0.2):
        raise LLMUnavailable("No LLM configured")
        yield ""  # pragma: no cover


def build_provider(settings: Settings) -> LLMProvider:
    if settings.minimax_api_key:
        return OpenAICompatProvider(
            settings.minimax_api_key, settings.llm_base_url,
            settings.llm_model, settings.llm_timeout_seconds)
    return NullProvider()


_FENCE_RX = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_reply(text: str) -> dict | None:
    """Defensive JSON extraction: strips fences, finds the outermost object."""
    cleaned = _FENCE_RX.sub("", text).strip()
    for candidate in (cleaned,):
        try:
            out = json.loads(candidate)
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if 0 <= start < end:
        try:
            out = json.loads(cleaned[start:end + 1])
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            return None
    return None

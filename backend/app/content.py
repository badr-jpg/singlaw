"""Editorial content for the UI: curated suggestion chips and "did you know"
discoveries, read from JSON under Settings.content_dir, with suggestions
merged against the questions real users actually ask."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

MAX_SUGGESTIONS = 4
POPULAR_SLOTS = 2        # at most this many of the chips come from real usage
POPULAR_LABEL = "Popular"
DISCOVERY_KEYS = ("id", "title", "body", "question", "citation", "url")


@lru_cache(maxsize=16)
def _read(path: str, mtime_ns: int) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load(path: Path) -> Any:
    """JSON file cached by (path, mtime): edits show up without a restart."""
    try:
        return _read(str(path), path.stat().st_mtime_ns)
    except FileNotFoundError:
        return None


def curated_suggestions(content_dir: Path, mode: str) -> list[dict[str, str]]:
    data = _load(content_dir / "suggestions.json") or {}
    return [{"label": str(i.get("label", "")), "text": str(i["text"]).strip()}
            for i in (data.get(mode) or []) if i.get("text")]


def merge_suggestions(
    curated: list[dict[str, str]], popular_questions: list[str],
    limit: int = MAX_SUGGESTIONS, popular_slots: int = POPULAR_SLOTS,
) -> list[dict[str, str]]:
    """Curated chips first, then up to `popular_slots` most-asked real questions
    (deduplicated against the curated texts, case-insensitively); `limit` total.
    A thin curated list lets more popular questions through."""
    seen = {c["text"].strip().lower() for c in curated}
    popular: list[dict[str, str]] = []
    for q in popular_questions:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            popular.append({"label": POPULAR_LABEL, "text": q.strip()})
    n_popular = min(len(popular), popular_slots)
    out = curated[: max(limit - n_popular, 0)] + popular[:n_popular]
    if len(out) < limit:
        out += popular[n_popular: n_popular + (limit - len(out))]
    return out[:limit]


def discoveries(content_dir: Path) -> list[dict[str, Any]]:
    data = _load(content_dir / "discoveries.json") or {}
    items = data.get("discoveries", []) if isinstance(data, dict) else data
    return [{k: i.get(k) for k in DISCOVERY_KEYS} for i in items]

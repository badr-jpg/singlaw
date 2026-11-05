"""Ingest pipeline: parsed documents → chunks → embeddings + sparse vectors →
Qdrant, with the corpus registry, citation graph and treatment pass."""
from __future__ import annotations

import asyncio
import shutil
import hashlib
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from app.context import AppContext
from app.ingest.chunker import (
    chunk_judgment,
    chunk_legislation,
    generic_chunks,
    slugify,
)
from app.ingest.citations import edges_from_paragraphs, resolve_treatment
from app.ingest.judgment_parser import parse_judgment
from app.ingest.sso_parser import parse_legislation
from app.llm import LLMUnavailable
from app.schemas import ChunkPayload
from app.vectorstore import SG_LAW, USER_DOCS

log = logging.getLogger(__name__)

_EMBED_BATCH = 32


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def upsert_chunks(ctx: AppContext, collection: str,
                        chunks: list[ChunkPayload]) -> int:
    """Embed (context-prepended, per contextual retrieval) and write to Qdrant."""
    for i in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[i:i + _EMBED_BATCH]
        texts = [f"{c.context}\n\n{c.text}".strip() for c in batch]
        dense = await ctx.registry.embed_docs(texts)
        sparse = await asyncio.to_thread(
            ctx.registry.sparse.encode_docs, texts, collection)
        await ctx.store.upsert_chunks(collection, batch, dense, sparse)
    return len(chunks)


async def ingest_legislation_html(
    ctx: AppContext, html: str, source_url: str = "",
    doc_type: str | None = None, fetched_at: str | None = None,
) -> tuple[str, int]:
    doc = parse_legislation(html, source_url=source_url, doc_type=doc_type)
    chunks = chunk_legislation(doc, as_at=date.today())
    if doc.unparsed:
        log.warning("%s: %d unparsed residue lines (first: %r)",
                    doc.title, len(doc.unparsed), doc.unparsed[0][:120])
    n = await upsert_chunks(ctx, SG_LAW, chunks)
    doc_id = chunks[0].doc_id if chunks else slugify(doc.title)
    await ctx.db.upsert_corpus_doc(
        doc_id=doc_id, title=doc.title, citation=doc.title,
        doc_type=doc.doc_type, status=doc.status,
        authority_tier=chunks[0].authority_tier if chunks else 6,
        source_url=source_url,
        sso_version_date=doc.sso_version_date.isoformat() if doc.sso_version_date else None,
        fetched_at=fetched_at or _now_iso(), chunk_count=n)
    return doc_id, n


async def ingest_judgment_html(
    ctx: AppContext, html: str, source_url: str = "",
    fetched_at: str | None = None,
) -> tuple[str, int]:
    j = parse_judgment(html, source_url=source_url)
    return await ingest_judgment(ctx, j, fetched_at=fetched_at)


async def ingest_judgment(
    ctx: AppContext, j, fetched_at: str | None = None,
    chunks: list[ChunkPayload] | None = None,
) -> tuple[str, int]:
    """Chunk, embed and register a parsed judgment, and add its citation edges.
    `chunks` overrides the default chunking for sources already split into passages."""
    source_url = j.source_url
    chunks = chunk_judgment(j) if chunks is None else chunks
    n = await upsert_chunks(ctx, SG_LAW, chunks)
    doc_id = chunks[0].doc_id if chunks else slugify(j.neutral_citation)
    await ctx.db.upsert_judgment(
        j.neutral_citation, j.case_name, j.court_code, j.court_level,
        j.decision_date.isoformat() if j.decision_date else None, doc_id)
    edges = edges_from_paragraphs(
        j.neutral_citation, [(p.number, p.text) for p in j.paragraphs])
    if not getattr(j, "numbered", True):
        for e in edges:
            e.paragraph = None  # sequence index, not a citable paragraph
    await ctx.db.add_citation_edges(edges)
    await ctx.db.upsert_corpus_doc(
        doc_id=doc_id, title=f"{j.case_name} {j.neutral_citation}",
        citation=j.neutral_citation, doc_type="judgment", status="in_force",
        authority_tier=chunks[0].authority_tier if chunks else 5,
        source_url=source_url, sso_version_date=None,
        fetched_at=fetched_at or _now_iso(), chunk_count=n)
    return doc_id, n


async def ingest_practice_direction_html(
    ctx: AppContext, html: str, title: str, source_url: str = "",
    fetched_at: str | None = None,
) -> tuple[str, int]:
    soup = BeautifulSoup(html, "lxml")
    text = "\n\n".join(
        t.get_text(" ", strip=True)
        for t in soup.find_all(["p", "div", "li", "h1", "h2", "h3"])
        if t.get_text(strip=True))
    chunks = generic_chunks(text, title=title, doc_type="practice_direction",
                            source_url=source_url)
    n = await upsert_chunks(ctx, SG_LAW, chunks)
    doc_id = chunks[0].doc_id if chunks else slugify(title)
    await ctx.db.upsert_corpus_doc(
        doc_id=doc_id, title=title, citation=title,
        doc_type="practice_direction", status="in_force", authority_tier=6,
        source_url=source_url, sso_version_date=None,
        fetched_at=fetched_at or _now_iso(), chunk_count=n)
    return doc_id, n


# ------------------------------------------------------------ treatment pass

async def run_treatment_pass(ctx: AppContext) -> dict[str, int]:
    """Fold citation-graph hints into per-judgment treatment (spec §2.5).

    Only later decisions count; "overruled" additionally requires the citing
    court to be same-or-higher level (enforced in resolve_treatment).
    """
    changed = 0
    judgments = await ctx.db.all_judgments()
    for row in judgments:
        inbound = await ctx.db.inbound_case_edges(row["citation"])
        hints: list[tuple[str, int, int]] = []
        for e in inbound:
            if (row["decision_date"] and e["citing_date"]
                    and e["citing_date"] <= row["decision_date"]):
                continue  # earlier or same-day decisions cannot affect treatment
            hints.append((e["treatment_hint"], e["citing_level"], row["court_level"]))
        treatment = resolve_treatment(hints)
        if treatment != row["treatment"]:
            await ctx.db.set_judgment_treatment(row["citation"], treatment)
            await ctx.store.set_payload_by_doc(
                SG_LAW, row["doc_id"], {"treatment": treatment})
            changed += 1
    return {"judgments": len(judgments), "treatment_updated": changed}


# ------------------------------------------------------------ user documents

def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    if suffix == ".docx":
        import docx

        return "\n\n".join(p.text for p in docx.Document(str(path)).paragraphs if p.text)
    return path.read_text(errors="replace")


async def _user_chunk_context(
    ctx: AppContext, filename: str, doc_head: str, idx: int, total: int, body: str,
) -> str:
    """LLM-derived context for user uploads (no structure to derive from),
    cached aggressively by content hash (spec §2.3)."""
    fallback = (
        f"This is part {idx} of {total} of '{filename}', a document uploaded by "
        "the user. It describes the user's factual situation and is not legal authority."
    )
    if not ctx.llm.configured:
        return fallback
    cache_dir = ctx.settings.cache_dir / "user_ctx"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{doc_head}\x00{body}".encode()).hexdigest()
    cached = cache_dir / f"{key}.txt"
    if cached.exists():
        return cached.read_text()
    try:
        reply = await ctx.llm.complete([
            {"role": "system", "content":
                "You write one- or two-sentence context strings that situate a "
                "chunk within its source document for search retrieval. Reply "
                "with the context only."},
            {"role": "user", "content":
                f"Document: {filename}\nDocument opening:\n{doc_head}\n\n"
                f"Chunk:\n{body[:2000]}\n\nContext:"},
        ], max_tokens=1500, model=ctx.settings.llm_fast_model or None)
        text = f"{reply.strip()} (From '{filename}', uploaded by the user; " \
               "factual background, not legal authority.)"
        cached.write_text(text)
        return text
    except LLMUnavailable:
        return fallback
    except Exception as exc:  # cache the fallback so we don't hammer a failing API
        log.warning("user-doc context LLM call failed: %s", exc)
        return fallback


async def seed_from_archive(ctx: AppContext, archive_dir: Path) -> dict[str, int]:
    """Load a pre-fetched corpus (manifest.json + HTML files) without crawling —
    the --seed-from-archive path for dev and offline distribution."""
    import json

    from app.ingest.archive import read_archived

    manifest = json.loads((archive_dir / "manifest.json").read_text())
    counts = {"legislation": 0, "judgment": 0, "practice_direction": 0, "chunks": 0}
    entries = manifest["documents"]
    # stop before indexing anything, not hours in or with a silently partial corpus
    missing = [e["path"] for e in entries if not (archive_dir / e["path"]).exists()]
    if missing:
        raise FileNotFoundError(
            f"manifest files missing from {archive_dir}: {', '.join(missing)}. "
            "See docs/CORPUS.md for how to get them.")
    for i, entry in enumerate(entries, start=1):
        path = archive_dir / entry["path"]
        kind = entry["kind"]
        url = entry.get("source_url", "")
        if kind == "sso_statutes_jsonl":  # Hugging Face copy of SSO legislation (clause 13)
            from app.ingest.sso_statutes import DEFAULT_MAX_CHARS as LEG_MAX
            from app.ingest.sso_statutes import ingest_sso_statutes

            c = await ingest_sso_statutes(
                ctx, path, doc_types=entry.get("doc_types"),
                max_chars=entry.get("max_chars", LEG_MAX), limit=entry.get("limit"))
            counts["legislation"] += c["documents"]
            counts["chunks"] += c["chunks"]
            continue
        if kind == "hf_judgment_passages":  # badlaldh/singapore-judgments, already split
            from app.ingest.hf_judgments import ingest_hf_judgments

            c = await ingest_hf_judgments(ctx, path)
            counts["judgment"] += c["documents"]
            counts["chunks"] += c["chunks"]
            continue
        html = read_archived(path)
        if i % 25 == 0:
            log.info("seeding %d/%d (%d chunks so far)", i, len(entries), counts["chunks"])
        if kind == "legislation":
            _, n = await ingest_legislation_html(
                ctx, html, source_url=url, doc_type=entry.get("doc_type"))
        elif kind == "judgment":
            _, n = await ingest_judgment_html(ctx, html, source_url=url)
        elif kind == "practice_direction":
            _, n = await ingest_practice_direction_html(
                ctx, html, title=entry.get("title", entry["path"]), source_url=url)
        else:
            log.warning("unknown manifest kind %r for %s", kind, entry["path"])
            continue
        counts[kind] += 1
        counts["chunks"] += n
    treatment = await run_treatment_pass(ctx)
    counts.update(treatment)
    await ctx.db.kv_set("last_seed", _now_iso())
    return counts


async def ingest_user_document(ctx: AppContext, document_id: str) -> None:
    row = await ctx.db.get_user_document(document_id)
    if not row:
        return
    await ctx.db.set_document_status(document_id, "processing")
    try:
        text = await asyncio.to_thread(_extract_text, Path(row["path"]))
        if not text.strip():
            raise ValueError("no extractable text in file")
        doc_id = f"user-{document_id}"
        chunks = generic_chunks(
            text, title=row["filename"], doc_type="user_document",
            collection=USER_DOCS, user_id=row["user_id"], doc_id=doc_id)
        doc_head = text[:1500]
        for i, c in enumerate(chunks, start=1):
            c.context = await _user_chunk_context(
                ctx, row["filename"], doc_head, i, len(chunks), c.text)
        n = await upsert_chunks(ctx, USER_DOCS, chunks)
        await ctx.db.set_document_status(document_id, "ready", chunk_count=n)
    except Exception as exc:
        log.exception("user document ingest failed")
        await ctx.db.set_document_status(document_id, "error", error=str(exc)[:500])


async def delete_user_document(ctx: AppContext, document_id: str) -> bool:
    """Remove a user document everywhere: its Qdrant points, its upload
    directory and its row. Shared by DELETE /api/documents/{id} and the
    business-delete cascade."""
    row = await ctx.db.get_user_document(document_id)
    if not row:
        return False
    await ctx.store.delete_doc(USER_DOCS, f"user-{document_id}")
    await ctx.db.delete_user_document(document_id)
    if row.get("path"):
        shutil.rmtree(Path(row["path"]).parent, ignore_errors=True)
    return True

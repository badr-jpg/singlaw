"""SQLite persistence: conversations, user documents, corpus registry,
citation graph, crawl state. WAL mode; all writes serialized through a
single writer guarded by an asyncio lock + flock-based election so multiple
uvicorn workers never interleave writes (spec Part 5)."""
from __future__ import annotations

import asyncio
import fcntl
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from app.ingest.citations import CitationEdge

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT 'New conversation',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '[]', meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS user_documents (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', chunk_count INTEGER NOT NULL DEFAULT 0,
  error TEXT, path TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS corpus_docs (
  doc_id TEXT PRIMARY KEY, title TEXT NOT NULL, citation TEXT NOT NULL DEFAULT '',
  doc_type TEXT NOT NULL, status TEXT NOT NULL, authority_tier INTEGER NOT NULL,
  source_url TEXT NOT NULL DEFAULT '', sso_version_date TEXT,
  fetched_at TEXT, chunk_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS doc_versions (
  doc_id TEXT NOT NULL, sso_version_date TEXT, fetched_at TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (doc_id, sso_version_date));
CREATE TABLE IF NOT EXISTS judgments (
  citation TEXT PRIMARY KEY, case_name TEXT NOT NULL, court_code TEXT NOT NULL,
  court_level INTEGER NOT NULL, decision_date TEXT, doc_id TEXT NOT NULL,
  treatment TEXT NOT NULL DEFAULT 'unknown');
CREATE TABLE IF NOT EXISTS citation_edges (
  citing TEXT NOT NULL, cited TEXT NOT NULL, kind TEXT NOT NULL,
  treatment_hint TEXT NOT NULL DEFAULT 'neutral', paragraph INTEGER,
  PRIMARY KEY (citing, cited, treatment_hint));
CREATE INDEX IF NOT EXISTS idx_edges_cited ON citation_edges(cited);
CREATE TABLE IF NOT EXISTS crawl_state (
  url TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  last_fetched TEXT, etag TEXT, error TEXT, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class Database:
    def __init__(self, path: Path):
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()
        self._flock_path = path.with_suffix(".writer.lock")

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=10000")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not opened"
        return self._conn

    @asynccontextmanager
    async def _write(self):
        """Single-writer election: in-process asyncio lock + cross-process flock."""
        async with self._write_lock:
            fd = open(self._flock_path, "w")
            await asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_EX)
            try:
                yield self.conn
                await self.conn.commit()
            except BaseException:
                await self.conn.rollback()
                raise
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()

    # ---------------- conversations ----------------

    async def create_conversation(self, title: str = "New conversation") -> str:
        cid = _new_id()
        async with self._write() as c:
            await c.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (cid, title, _now(), _now()))
        return cid

    async def list_conversations(self) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            """SELECT c.*, COUNT(m.id) AS message_count FROM conversations c
               LEFT JOIN messages m ON m.conversation_id = c.id
               GROUP BY c.id ORDER BY c.updated_at DESC""")
        return [dict(r) for r in await cur.fetchall()]

    async def get_conversation(self, cid: str) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM conversations WHERE id=?", (cid,))
        row = await cur.fetchone()
        if not row:
            return None
        cur = await self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (cid,))
        msgs = []
        for m in await cur.fetchall():
            d = dict(m)
            d["sources"] = json.loads(d["sources"])
            d["meta"] = json.loads(d["meta"])
            msgs.append(d)
        return {**dict(row), "messages": msgs}

    async def rename_conversation(self, cid: str, title: str) -> bool:
        async with self._write() as c:
            cur = await c.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
                (title, _now(), cid))
            return cur.rowcount > 0

    async def delete_conversation(self, cid: str) -> bool:
        async with self._write() as c:
            cur = await c.execute("DELETE FROM conversations WHERE id=?", (cid,))
            return cur.rowcount > 0

    async def add_message(
        self, cid: str, role: str, content: str,
        sources: list[dict] | None = None, meta: dict | None = None,
    ) -> str:
        mid = _new_id()
        async with self._write() as c:
            await c.execute(
                "INSERT INTO messages (id, conversation_id, role, content, sources, meta, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (mid, cid, role, content, json.dumps(sources or []),
                 json.dumps(meta or {}), _now()))
            await c.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?", (_now(), cid))
        return mid

    async def message_history(self, cid: str, limit: int = 12) -> list[dict[str, str]]:
        cur = await self.conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? "
            "ORDER BY created_at DESC LIMIT ?", (cid, limit))
        rows = [dict(r) for r in await cur.fetchall()]
        return list(reversed(rows))

    # ---------------- user documents ----------------

    async def add_user_document(self, user_id: str, filename: str, path: str) -> str:
        did = _new_id()
        async with self._write() as c:
            await c.execute(
                "INSERT INTO user_documents (id, user_id, filename, path, created_at) "
                "VALUES (?,?,?,?,?)", (did, user_id, filename, path, _now()))
        return did

    async def set_document_path(self, did: str, path: str) -> None:
        async with self._write() as c:
            await c.execute("UPDATE user_documents SET path=? WHERE id=?", (path, did))

    async def set_document_status(
        self, did: str, status: str, chunk_count: int | None = None,
        error: str | None = None,
    ) -> None:
        async with self._write() as c:
            await c.execute(
                "UPDATE user_documents SET status=?, chunk_count=COALESCE(?, chunk_count), error=? WHERE id=?",
                (status, chunk_count, error, did))

    async def list_user_documents(self, user_id: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM user_documents WHERE user_id=? ORDER BY created_at DESC",
            (user_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def get_user_document(self, did: str) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM user_documents WHERE id=?", (did,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_user_document(self, did: str) -> bool:
        async with self._write() as c:
            cur = await c.execute("DELETE FROM user_documents WHERE id=?", (did,))
            return cur.rowcount > 0

    # ---------------- corpus registry ----------------

    async def upsert_corpus_doc(self, **kw: Any) -> None:
        async with self._write() as c:
            await c.execute(
                """INSERT INTO corpus_docs (doc_id, title, citation, doc_type, status,
                     authority_tier, source_url, sso_version_date, fetched_at, chunk_count)
                   VALUES (:doc_id, :title, :citation, :doc_type, :status,
                     :authority_tier, :source_url, :sso_version_date, :fetched_at, :chunk_count)
                   ON CONFLICT(doc_id) DO UPDATE SET title=:title, citation=:citation,
                     doc_type=:doc_type, status=:status, authority_tier=:authority_tier,
                     source_url=:source_url, sso_version_date=:sso_version_date,
                     fetched_at=:fetched_at, chunk_count=:chunk_count""", kw)
            await c.execute(
                """INSERT OR REPLACE INTO doc_versions (doc_id, sso_version_date, fetched_at, source_url)
                   VALUES (?,?,?,?)""",
                (kw["doc_id"], kw.get("sso_version_date"), kw.get("fetched_at"),
                 kw.get("source_url", "")))

    async def list_corpus(
        self, q: str | None = None, doc_type: str | None = None, limit: int = 500,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM corpus_docs WHERE 1=1"
        args: list[Any] = []
        if q:
            sql += " AND (title LIKE ? OR citation LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        if doc_type:
            sql += " AND doc_type=?"
            args.append(doc_type)
        sql += " ORDER BY title LIMIT ?"
        args.append(limit)
        cur = await self.conn.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]

    async def get_corpus_doc(self, doc_id: str) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM corpus_docs WHERE doc_id=?", (doc_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def corpus_counts(self) -> dict[str, int]:
        cur = await self.conn.execute(
            "SELECT doc_type, COUNT(*) n FROM corpus_docs GROUP BY doc_type")
        counts = {r["doc_type"]: r["n"] for r in await cur.fetchall()}
        cur = await self.conn.execute(
            "SELECT COUNT(*) n FROM corpus_docs WHERE status='repealed'")
        counts["repealed"] = (await cur.fetchone())["n"]
        return counts

    async def doc_versions(self, doc_id: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM doc_versions WHERE doc_id=? ORDER BY sso_version_date DESC",
            (doc_id,))
        return [dict(r) for r in await cur.fetchall()]

    # ---------------- citation graph ----------------

    async def upsert_judgment(
        self, citation: str, case_name: str, court_code: str, court_level: int,
        decision_date: str | None, doc_id: str,
    ) -> None:
        async with self._write() as c:
            await c.execute(
                """INSERT INTO judgments (citation, case_name, court_code, court_level, decision_date, doc_id)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(citation) DO UPDATE SET case_name=excluded.case_name,
                     court_code=excluded.court_code, court_level=excluded.court_level,
                     decision_date=excluded.decision_date, doc_id=excluded.doc_id""",
                (citation, case_name, court_code, court_level, decision_date, doc_id))

    async def add_citation_edges(self, edges: list[CitationEdge]) -> None:
        if not edges:
            return
        async with self._write() as c:
            await c.executemany(
                "INSERT OR IGNORE INTO citation_edges (citing, cited, kind, treatment_hint, paragraph) "
                "VALUES (?,?,?,?,?)",
                [(e.citing, e.cited, e.kind, e.treatment_hint, e.paragraph) for e in edges])

    async def citing_of(self, cited: str) -> list[dict[str, Any]]:
        """Judgments citing a case or provision, with citing-court metadata."""
        cur = await self.conn.execute(
            """SELECT e.citing AS citation, e.treatment_hint, e.paragraph,
                      j.case_name, j.court_code, j.court_level, j.decision_date,
                      j.treatment AS citing_treatment
               FROM citation_edges e LEFT JOIN judgments j ON j.citation = e.citing
               WHERE e.cited = :c OR e.cited LIKE :c || '(%'
                  OR e.cited LIKE :c || ', s %'
               ORDER BY j.decision_date DESC""", {"c": cited})
        return [dict(r) for r in await cur.fetchall()]

    async def all_judgments(self) -> list[dict[str, Any]]:
        cur = await self.conn.execute("SELECT * FROM judgments")
        return [dict(r) for r in await cur.fetchall()]

    async def inbound_case_edges(self, cited: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            """SELECT e.*, j.court_level AS citing_level, j.decision_date AS citing_date
               FROM citation_edges e JOIN judgments j ON j.citation = e.citing
               WHERE e.cited=? AND e.kind='case'""", (cited,))
        return [dict(r) for r in await cur.fetchall()]

    async def set_judgment_treatment(self, citation: str, treatment: str) -> None:
        async with self._write() as c:
            await c.execute(
                "UPDATE judgments SET treatment=? WHERE citation=?", (treatment, citation))

    async def get_judgment(self, citation: str) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM judgments WHERE citation=?", (citation,))
        row = await cur.fetchone()
        return dict(row) if row else None

    # ---------------- crawl state / kv ----------------

    async def enqueue_url(self, url: str, kind: str) -> None:
        async with self._write() as c:
            await c.execute(
                "INSERT OR IGNORE INTO crawl_state (url, kind, added_at) VALUES (?,?,?)",
                (url, kind, _now()))

    async def pending_urls(self, limit: int = 100) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM crawl_state WHERE status IN ('pending','error') "
            "ORDER BY added_at LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

    async def mark_url(self, url: str, status: str, error: str | None = None,
                       etag: str | None = None) -> None:
        async with self._write() as c:
            await c.execute(
                "UPDATE crawl_state SET status=?, error=?, etag=COALESCE(?, etag), last_fetched=? WHERE url=?",
                (status, error, etag, _now(), url))

    async def kv_get(self, key: str) -> str | None:
        cur = await self.conn.execute("SELECT value FROM kv WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def kv_set(self, key: str, value: str) -> None:
        async with self._write() as c:
            await c.execute(
                "INSERT INTO kv (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

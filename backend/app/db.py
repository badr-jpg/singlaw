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
from datetime import UTC, datetime, timedelta
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
-- v2 (2026-10-07): business workspaces, answer feedback, billing waitlist
CREATE TABLE IF NOT EXISTS businesses (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT 'Building2',
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS message_feedback (
  message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
  rating TEXT NOT NULL, comment TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS billing_waitlist (
  email TEXT NOT NULL, plan_id TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (email, plan_id));
"""

# Columns added to pre-existing tables after their first release. Applied
# idempotently in open(); CREATE TABLE IF NOT EXISTS cannot add columns.
_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, ALTER TABLE ... ADD COLUMN clause)
    ("user_documents", "business_id", "business_id TEXT"),
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


new_id = _new_id  # public alias for callers that pre-assign ids


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
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Idempotent column additions, guarded by PRAGMA table_info."""
        for table, column, clause in _MIGRATIONS:
            cur = await self.conn.execute(f"PRAGMA table_info({table})")
            if column not in {r["name"] for r in await cur.fetchall()}:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {clause}")

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
            """SELECT m.*, f.rating AS feedback FROM messages m
               LEFT JOIN message_feedback f ON f.message_id = m.id
               WHERE m.conversation_id=? ORDER BY m.created_at""", (cid,))
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
        message_id: str | None = None,
    ) -> str:
        mid = message_id or _new_id()
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

    async def get_message(self, mid: str) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM messages WHERE id=?", (mid,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def last_user_message(self, cid: str) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? AND role='user' "
            "ORDER BY created_at DESC LIMIT 1", (cid,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_last_assistant_message(self, cid: str) -> bool:
        """Regenerate support: drop the conversation's final message if (and
        only if) it is an assistant turn. An earlier assistant turn is never
        touched, so a user message whose answer failed is simply re-answered."""
        async with self._write() as c:
            cur = await c.execute(
                """DELETE FROM messages WHERE role='assistant' AND id = (
                     SELECT id FROM messages WHERE conversation_id=?
                     ORDER BY created_at DESC LIMIT 1)""", (cid,))
            return cur.rowcount > 0

    async def top_user_questions(
        self, days: int = 30, min_count: int = 3, limit: int = 4,
    ) -> list[dict[str, Any]]:
        """Most-asked user questions (identical after trim/lower-case) in the
        window — feeds /api/content/suggestions."""
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        cur = await self.conn.execute(
            """SELECT content, COUNT(*) AS n FROM messages
               WHERE role='user' AND created_at >= ?
                 AND length(trim(content)) BETWEEN 8 AND 200
               GROUP BY lower(trim(content)) HAVING n >= ?
               ORDER BY n DESC, MAX(created_at) DESC LIMIT ?""",
            (since, min_count, limit))
        return [dict(r) for r in await cur.fetchall()]

    # ---------------- feedback ----------------

    async def upsert_feedback(self, mid: str, rating: str, comment: str | None) -> None:
        async with self._write() as c:
            await c.execute(
                """INSERT INTO message_feedback (message_id, rating, comment, created_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(message_id) DO UPDATE SET rating=excluded.rating,
                     comment=excluded.comment, created_at=excluded.created_at""",
                (mid, rating, comment, _now()))

    # ---------------- businesses ----------------

    _BUSINESS_SELECT = """SELECT b.*, COUNT(d.id) AS document_count FROM businesses b
               LEFT JOIN user_documents d ON d.business_id = b.id"""

    async def create_business(
        self, user_id: str, name: str, description: str = "", icon: str = "Building2",
    ) -> str:
        bid = _new_id()
        async with self._write() as c:
            await c.execute(
                "INSERT INTO businesses (id, user_id, name, description, icon, created_at) "
                "VALUES (?,?,?,?,?,?)", (bid, user_id, name, description, icon, _now()))
        return bid

    async def list_businesses(self, user_id: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            self._BUSINESS_SELECT + " WHERE b.user_id=? GROUP BY b.id ORDER BY b.created_at",
            (user_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def get_business(self, bid: str) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            self._BUSINESS_SELECT + " WHERE b.id=? GROUP BY b.id", (bid,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def count_businesses(self, user_id: str) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) n FROM businesses WHERE user_id=?", (user_id,))
        return (await cur.fetchone())["n"]

    async def update_business(self, bid: str, **fields: Any) -> bool:
        allowed = {k: v for k, v in fields.items()
                   if k in ("name", "description", "icon") and v is not None}
        if not allowed:
            return await self.get_business(bid) is not None
        sets = ", ".join(f"{k}=?" for k in allowed)
        async with self._write() as c:
            cur = await c.execute(
                f"UPDATE businesses SET {sets} WHERE id=?", (*allowed.values(), bid))
            return cur.rowcount > 0

    async def delete_business(self, bid: str) -> bool:
        async with self._write() as c:
            cur = await c.execute("DELETE FROM businesses WHERE id=?", (bid,))
            return cur.rowcount > 0

    # ---------------- billing ----------------

    async def usage_counts(self, user_id: str) -> dict[str, int]:
        cur = await self.conn.execute(
            """SELECT (SELECT COUNT(*) FROM conversations) AS conversations,
                      (SELECT COUNT(*) FROM messages) AS messages,
                      (SELECT COUNT(*) FROM user_documents WHERE user_id=?) AS documents,
                      (SELECT COUNT(*) FROM businesses WHERE user_id=?) AS businesses""",
            (user_id, user_id))
        return dict(await cur.fetchone())

    async def add_waitlist(self, email: str, plan_id: str) -> None:
        async with self._write() as c:
            await c.execute(
                "INSERT OR IGNORE INTO billing_waitlist (email, plan_id, created_at) VALUES (?,?,?)",
                (email, plan_id, _now()))

    async def waitlist_entries(self) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM billing_waitlist ORDER BY created_at")
        return [dict(r) for r in await cur.fetchall()]

    # ---------------- user documents ----------------

    async def add_user_document(
        self, user_id: str, filename: str, path: str, business_id: str | None = None,
    ) -> str:
        did = _new_id()
        async with self._write() as c:
            await c.execute(
                "INSERT INTO user_documents (id, user_id, filename, path, business_id, created_at) "
                "VALUES (?,?,?,?,?,?)", (did, user_id, filename, path, business_id, _now()))
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

    async def list_user_documents(
        self, user_id: str, business_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """All of the user's documents, or only those of one business."""
        sql = "SELECT * FROM user_documents WHERE user_id=?"
        args: list[Any] = [user_id]
        if business_id is not None:
            sql += " AND business_id=?"
            args.append(business_id)
        cur = await self.conn.execute(sql + " ORDER BY created_at DESC", args)
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

"""Opening a pre-v2 database must add the new column idempotently."""
import sqlite3

from app.db import Database

_OLD_USER_DOCUMENTS = """
CREATE TABLE user_documents (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', chunk_count INTEGER NOT NULL DEFAULT 0,
  error TEXT, path TEXT, created_at TEXT NOT NULL);
INSERT INTO user_documents (id, user_id, filename, created_at)
  VALUES ('olddoc', 'local', 'old.txt', '2026-01-01T00:00:00+00:00');
"""


async def test_open_migrates_pre_v2_user_documents(tmp_path):
    path = tmp_path / "app.sqlite3"
    with sqlite3.connect(path) as raw:
        raw.executescript(_OLD_USER_DOCUMENTS)

    for _ in range(2):  # second open must be a no-op, not a duplicate-column error
        db = Database(path)
        await db.open()
        cur = await db.conn.execute("PRAGMA table_info(user_documents)")
        assert "business_id" in {r["name"] for r in await cur.fetchall()}
        await db.close()

    db = Database(path)
    await db.open()
    try:
        old = await db.get_user_document("olddoc")
        assert old is not None and old["business_id"] is None
        bid = await db.create_business("local", "Kopi Corner")
        did = await db.add_user_document("local", "new.txt", "", business_id=bid)
        assert [d["id"] for d in await db.list_user_documents("local", business_id=bid)] == [did]
        assert {d["id"] for d in await db.list_user_documents("local")} == {"olddoc", did}
        assert (await db.get_business(bid))["document_count"] == 1
        # v2 tables exist too
        for table in ("businesses", "message_feedback", "billing_waitlist"):
            cur = await db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            assert await cur.fetchone(), table
    finally:
        await db.close()

"""The Source library lists the corpus from list_corpus, so it must return every document."""
from app.db import Database


async def test_list_corpus_returns_every_document(tmp_path):
    db = Database(tmp_path / "app.sqlite3")
    await db.open()
    try:
        for i in range(726):
            await db.upsert_corpus_doc(
                doc_id=f"doc-{i:03}", title=f"Act {i:03}", citation=f"Act {i:03}",
                doc_type="act", status="in_force", authority_tier=2, source_url="",
                sso_version_date=None, fetched_at="2026-01-01T00:00:00+00:00", chunk_count=1)
        assert len(await db.list_corpus()) == 726
    finally:
        await db.close()

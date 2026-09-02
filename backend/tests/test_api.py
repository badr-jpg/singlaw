import asyncio
import urllib.parse

import httpx
import pytest

from app.crawler import window_from_settings
from app.main import create_app


@pytest.fixture(scope="session")
async def client(ctx):
    app = create_app()
    app.state.ctx = ctx  # bypass lifespan; session ctx already built on stubs
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as c:
        yield c


async def test_health(client):
    r = await client.get("/api/health")
    r.raise_for_status()
    body = r.json()
    assert body["models"]["loaded"] is True
    assert body["qdrant"]["sg_law"] > 0
    assert body["corpus"]["acts"] >= 3
    assert body["corpus"]["judgments"] == 3
    assert body["llm"]["configured"] is False


async def test_search_endpoint_with_debug(client):
    r = await client.post("/api/search", json={
        "query": "dismissal for misconduct due inquiry",
        "top_k": 10, "include_debug": True})
    r.raise_for_status()
    body = r.json()
    assert body["results"]
    first = body["results"][0]
    for key in ("citation", "ce_score", "authority_score", "final_score", "text"):
        assert key in first
    assert body["debug"] is not None
    assert "timings_ms" in body["debug"]


async def test_law_lookup_and_citing(client):
    cite = urllib.parse.quote("Employment Act 1968, s 14", safe="")
    r = await client.get(f"/api/law/{cite}")
    r.raise_for_status()
    body = r.json()
    assert body["found"]
    assert body["chunks"][0]["citation"] == "Employment Act 1968, s 14"

    r = await client.get(f"/api/law/{cite}/citing")
    assert any(c["citation"] == "[2022] SGCA 60" for c in r.json()["citing"])

    r = await client.get(f"/api/law/{cite}/history")
    r.raise_for_status()
    assert r.json()["versions"]


async def test_corpus_explorer_flow(client):
    r = await client.get("/api/corpus/toc", params={"doc_type": "act"})
    r.raise_for_status()
    toc = r.json()
    ea = next(d for d in toc if d["title"] == "Employment Act 1968")

    r = await client.get(f"/api/corpus/doc/{ea['doc_id']}")
    r.raise_for_status()
    tree = r.json()["tree"]
    labels = [n["label"] for n in tree]
    assert any("Part 2" in l for l in labels)
    part2 = next(n for n in tree if "Part 2" in n["label"])
    leaf = next(n for n in part2["children"] if "Section 14" in n["label"])

    r = await client.get(f"/api/chunks/{leaf['chunk_id']}")
    r.raise_for_status()
    assert "after due inquiry" in r.json()["text"]


async def test_chat_then_conversation_crud(client):
    r = await client.post("/api/chat", json={
        "message": "what notice does the practice direction require for originating claims"})
    r.raise_for_status()
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: sources" in r.text and "event: done" in r.text

    convs = (await client.get("/api/conversations")).json()
    assert convs and convs[0]["message_count"] == 2
    cid = convs[0]["id"]

    r = await client.patch(f"/api/conversations/{cid}", json={"title": "PD question"})
    r.raise_for_status()
    conv = (await client.get(f"/api/conversations/{cid}")).json()
    assert conv["title"] == "PD question"
    assert conv["messages"][-1]["role"] == "assistant"
    assert conv["messages"][-1]["meta"]["disclaimer"]

    assert (await client.delete(f"/api/conversations/{cid}")).status_code == 204
    assert (await client.get(f"/api/conversations/{cid}")).status_code == 404


async def test_document_upload_ingest_and_delete(client, ctx):
    content = (b"TENANCY AGREEMENT\n\nThe tenant shall pay a security deposit of "
               b"two months' rent, refundable within 14 days of the expiry of the "
               b"term less deductions for damage beyond fair wear and tear.\n\n"
               b"The landlord may terminate on one month's notice for non-payment.")
    r = await client.post("/api/documents",
                          files={"file": ("tenancy.txt", content, "text/plain")})
    r.raise_for_status()
    did = r.json()["id"]

    for _ in range(50):
        docs = (await client.get("/api/documents")).json()
        doc = next(d for d in docs if d["id"] == did)
        if doc["status"] in ("ready", "error"):
            break
        await asyncio.sleep(0.1)
    assert doc["status"] == "ready"
    assert doc["chunk_count"] >= 1

    # scoped retrieval sees the user's document alongside sg_law
    r = await client.post("/api/search", json={
        "query": "security deposit refund tenancy", "doc_ids": [did]})
    results = r.json()["results"]
    assert any(x["collection"] == "user_docs" for x in results)

    assert (await client.delete(f"/api/documents/{did}")).status_code == 204
    docs = (await client.get("/api/documents")).json()
    assert not any(d["id"] == did for d in docs)


async def test_admin_sync_respects_window(client, ctx):
    r = await client.post("/api/admin/sync", json={"force": False})
    r.raise_for_status()
    body = r.json()
    if not window_from_settings(ctx.settings).is_open():
        assert body["started"] is False
        assert "05:00" in body["reason"]


async def test_unsupported_upload_type_rejected(client):
    r = await client.post("/api/documents",
                          files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415

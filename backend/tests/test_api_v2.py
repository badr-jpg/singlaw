"""API Contract v2 addendum (2026-10-07): chat regenerate/business scoping,
conversation creation, businesses, feedback, content, billing."""
import asyncio
import hashlib
import hmac
import json
import time
from pathlib import Path

from app.billing import PLANS


# ---------------------------------------------------------------- helpers

def sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.strip().split("\n\n"):
        ev, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                ev = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if ev:
            events.append((ev, data))
    return events


def by_event(events, name):
    return [d for e, d in events if e == name]


async def chat(client, **body):
    r = await client.post("/api/chat", json=body)
    r.raise_for_status()
    return sse_events(r.text)


async def wait_ready(client, did: str) -> dict:
    for _ in range(100):
        docs = (await client.get("/api/documents")).json()
        doc = next(d for d in docs if d["id"] == did)
        if doc["status"] in ("ready", "error"):
            return doc
        await asyncio.sleep(0.1)
    return doc


async def delete_conversation(client, cid: str):
    await client.delete(f"/api/conversations/{cid}")


# ---------------------------------------------------------------- conversations

async def test_create_empty_conversation(client):
    r = await client.post("/api/conversations", json={"title": None})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "title", "created_at", "updated_at", "message_count"}
    assert body["message_count"] == 0 and body["title"] == "New conversation"
    conv = (await client.get(f"/api/conversations/{body['id']}")).json()
    assert conv["messages"] == []

    r2 = await client.post("/api/conversations", json={"title": "  Dismissal  "})
    assert r2.status_code == 201 and r2.json()["title"] == "Dismissal"
    for cid in (body["id"], r2.json()["id"]):
        await delete_conversation(client, cid)


async def test_empty_conversation_is_titled_by_first_message(client):
    cid = (await client.post("/api/conversations", json={})).json()["id"]
    q = "what annual leave is a part-time employee entitled to"
    events = await chat(client, message=q, conversation_id=cid)
    assert by_event(events, "done")
    assert by_event(events, "meta")[0]["conversation_id"] == cid
    conv = (await client.get(f"/api/conversations/{cid}")).json()
    assert conv["title"] == q
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    await delete_conversation(client, cid)


async def test_regenerate_replaces_last_assistant_turn(client):
    q = "can my employer dismiss me for misconduct without an inquiry"
    events = await chat(client, message=q)
    cid = by_event(events, "meta")[0]["conversation_id"]
    first_mid = by_event(events, "done")[0]["message_id"]
    conv = (await client.get(f"/api/conversations/{cid}")).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["id"] == first_mid

    events = await chat(client, message="", conversation_id=cid, regenerate=True)
    assert not by_event(events, "error"), events
    assert by_event(events, "meta")[0]["conversation_id"] == cid
    assert [e for e, _ in events] == ["meta", "sources", "token", "validation", "done"]
    new_mid = by_event(events, "done")[0]["message_id"]
    assert new_mid != first_mid
    text = "".join(d["text"] for d in by_event(events, "token"))
    assert "[CITE:" in text  # offline extractive fallback re-answered the question

    conv = (await client.get(f"/api/conversations/{cid}")).json()
    msgs = conv["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]  # no new user turn
    assert msgs[0]["content"] == q
    assert msgs[1]["id"] == new_mid and first_mid not in {m["id"] for m in msgs}
    assert msgs[1]["meta"]["business_id"] is None
    await delete_conversation(client, cid)


async def test_regenerate_and_blank_message_errors(client):
    events = await chat(client, message="", regenerate=True)
    assert "conversation_id" in by_event(events, "error")[0]["message"]
    events = await chat(client, message="", conversation_id="nope", regenerate=True)
    assert by_event(events, "error")
    events = await chat(client, message="   ")
    assert "message is required" in by_event(events, "error")[0]["message"]
    # an empty conversation (no user turn yet) cannot be regenerated
    cid = (await client.post("/api/conversations", json={})).json()["id"]
    events = await chat(client, message="", conversation_id=cid, regenerate=True)
    assert "no user message" in by_event(events, "error")[0]["message"]
    await delete_conversation(client, cid)


# ---------------------------------------------------------------- businesses

async def test_business_crud_documents_chat_and_cascade(client, ctx):
    r = await client.post("/api/businesses", json={
        "name": "Kopi Corner",
        "description": "A neighbourhood cafe with six part-time baristas"})
    assert r.status_code == 201
    b = r.json()
    assert set(b) == {"id", "name", "description", "icon", "document_count", "created_at"}
    assert b["icon"] == "Building2" and b["document_count"] == 0
    bid = b["id"]
    assert any(x["id"] == bid for x in (await client.get("/api/businesses")).json())

    r = await client.patch(f"/api/businesses/{bid}",
                           json={"name": "Kopi Corner Pte Ltd", "icon": "Coffee"})
    r.raise_for_status()
    assert r.json()["name"] == "Kopi Corner Pte Ltd" and r.json()["icon"] == "Coffee"
    assert r.json()["description"] == b["description"]
    assert (await client.patch("/api/businesses/nope", json={"name": "x"})).status_code == 404
    assert (await client.patch(f"/api/businesses/{bid}", json={"name": "   "})).status_code == 422

    # upload into the business
    content = (b"Kopi Corner staff handbook\n\nOur part-time baristas work 20 hours a "
               b"week. Annual leave for part-time baristas is pro-rated to the hours "
               b"worked compared with a full-time barista on 44 hours.\n")
    r = await client.post("/api/documents", data={"business_id": bid},
                          files={"file": ("handbook.txt", content, "text/plain")})
    r.raise_for_status()
    assert r.json()["business_id"] == bid
    did = r.json()["id"]
    doc = await wait_ready(client, did)
    assert doc["status"] == "ready" and doc["business_id"] == bid
    biz_docs = (await client.get(f"/api/businesses/{bid}/documents")).json()
    assert [d["id"] for d in biz_docs] == [did]
    assert set(biz_docs[0]) == set(doc)  # same shape as GET /api/documents
    listed = next(x for x in (await client.get("/api/businesses")).json() if x["id"] == bid)
    assert listed["document_count"] == 1
    r = await client.post("/api/documents", data={"business_id": "nope"},
                          files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 404

    # chat scoped to the business sees its document and reports business_id
    events = await chat(client, business_id=bid,
                        message="how much annual leave are my part-time baristas entitled to")
    meta = by_event(events, "meta")[0]
    assert meta["business_id"] == bid
    sources = by_event(events, "sources")[0]["sources"]
    assert any(s["collection"] == "user_docs" for s in sources)
    assert by_event(events, "done")
    cid = meta["conversation_id"]
    stored = (await client.get(f"/api/conversations/{cid}")).json()["messages"][-1]
    assert stored["meta"]["business_id"] == bid

    events = await chat(client, message="hello there", business_id="nope")
    assert "not found" in by_event(events, "error")[0]["message"]

    # delete cascades: rows, files, Qdrant points
    upload_dir = Path((await ctx.db.get_user_document(did))["path"]).parent
    assert upload_dir.exists()
    assert (await client.delete(f"/api/businesses/{bid}")).status_code == 204
    assert await ctx.db.get_business(bid) is None
    assert await ctx.db.get_user_document(did) is None
    assert not upload_dir.exists()
    assert (await client.get(f"/api/businesses/{bid}/documents")).status_code == 404
    assert (await client.delete(f"/api/businesses/{bid}")).status_code == 404
    r = await client.post("/api/search", json={
        "query": "part-time baristas annual leave", "doc_ids": [did]})
    assert not any(x["collection"] == "user_docs" for x in r.json()["results"])
    await delete_conversation(client, cid)


async def test_business_limit_follows_the_active_plan(client, ctx):
    from app.billing import active_plan, effective_limit

    plan = await active_plan(ctx.db)
    limit = effective_limit(plan["limits"]["businesses"], ctx.settings.max_businesses)
    assert limit is not None
    existing = await ctx.db.count_businesses(ctx.settings.user_id)
    created = []
    for i in range(limit - existing):
        r = await client.post("/api/businesses", json={"name": f"Biz {i}"})
        assert r.status_code == 201
        created.append(r.json()["id"])
    r = await client.post("/api/businesses", json={"name": "One too many"})
    assert r.status_code == 403
    assert "detail" in r.json() and str(limit) in r.json()["detail"]
    for bid in created:
        assert (await client.delete(f"/api/businesses/{bid}")).status_code == 204


class CapturingProvider:
    """Fake LLM: records the generation messages, streams a cited answer."""

    name = "fake"
    configured = True

    def __init__(self):
        self.captured: list[list[dict]] = []

    async def complete(self, messages, **kw):
        return "no json here"  # analysis/rewrite fall back to heuristics

    async def stream(self, messages, **kw):
        self.captured.append(messages)
        yield ("As at 2026-10-07, an employer may dismiss an employee for "
               "misconduct only after due inquiry [CITE:1].")


async def test_business_profile_reaches_generation_as_context(client, ctx):
    r = await client.post("/api/businesses", json={
        "name": "Lim Logistics", "description": "A freight forwarder with 40 warehouse staff"})
    bid = r.json()["id"]
    provider = CapturingProvider()
    original = ctx.llm
    ctx.llm = provider
    try:
        events = await chat(client, business_id=bid,
                            message="can I dismiss a warehouse employee for misconduct")
    finally:
        ctx.llm = original
    assert by_event(events, "done")
    user_turn = provider.captured[0][-1]["content"]
    assert "USER CONTEXT" in user_turn and "not legal authority" in user_turn
    assert "The user runs a business: Lim Logistics. A freight forwarder" in user_turn
    assert user_turn.index("SOURCES:") < user_turn.index("USER CONTEXT") < user_turn.index("QUESTION:")
    await delete_conversation(client, by_event(events, "meta")[0]["conversation_id"])
    assert (await client.delete(f"/api/businesses/{bid}")).status_code == 204


# ---------------------------------------------------------------- feedback

async def test_feedback_upsert_reflected_in_conversation(client):
    events = await chat(client, message="what notice does the practice direction require")
    cid = by_event(events, "meta")[0]["conversation_id"]
    mid = by_event(events, "done")[0]["message_id"]
    conv = (await client.get(f"/api/conversations/{cid}")).json()
    assert all(m["feedback"] is None for m in conv["messages"])

    r = await client.post("/api/feedback", json={"message_id": mid, "rating": "up"})
    assert r.status_code == 201 and r.json() == {"ok": True}
    conv = (await client.get(f"/api/conversations/{cid}")).json()
    assert conv["messages"][-1]["feedback"] == "up"
    assert conv["messages"][0]["feedback"] is None

    r = await client.post("/api/feedback", json={
        "message_id": mid, "rating": "down", "comment": "cited the wrong section"})
    assert r.status_code == 201
    conv = (await client.get(f"/api/conversations/{cid}")).json()
    assert conv["messages"][-1]["feedback"] == "down"

    assert (await client.post("/api/feedback", json={
        "message_id": "nope", "rating": "up"})).status_code == 404
    assert (await client.post("/api/feedback", json={
        "message_id": mid, "rating": "meh"})).status_code == 422
    await delete_conversation(client, cid)


# ---------------------------------------------------------------- content

async def test_suggestions_shape_and_modes(client):
    texts = {}
    for mode in ("personal", "business"):
        r = await client.get("/api/content/suggestions", params={"mode": mode})
        r.raise_for_status()
        items = r.json()["suggestions"]
        assert 1 <= len(items) <= 4
        for i in items:
            assert set(i) == {"label", "text"} and i["label"] and i["text"]
        texts[mode] = {i["text"] for i in items}
    assert texts["personal"] != texts["business"]
    default = (await client.get("/api/content/suggestions")).json()["suggestions"]
    assert {i["text"] for i in default} == texts["personal"]
    assert (await client.get("/api/content/suggestions",
                             params={"mode": "enterprise"})).status_code == 422


async def test_suggestions_merge_popular_user_questions(client, ctx):
    q = "What notice must a landlord give to end a tenancy early?"
    cid = await ctx.db.create_conversation("popular")
    try:
        for _ in range(4):
            await ctx.db.add_message(cid, "user", q)
        items = (await client.get("/api/content/suggestions",
                                  params={"mode": "personal"})).json()["suggestions"]
        assert len(items) <= 4
        popular = [i for i in items if i["label"] == "Popular"]
        assert q in [p["text"] for p in popular]
        assert items[0]["label"] != "Popular"  # curated first
    finally:
        await ctx.db.delete_conversation(cid)


async def test_discoveries_shape(client):
    r = await client.get("/api/content/discoveries")
    r.raise_for_status()
    items = r.json()["discoveries"]
    assert len(items) == 5
    for i in items:
        assert set(i) == {"id", "title", "body", "question", "citation", "url"}
        assert all(i[k] for k in i)
        assert i["url"].startswith("https://")
    assert len({i["id"] for i in items}) == 5


# ---------------------------------------------------------------- billing

async def test_billing_plans(client):
    r = await client.get("/api/billing/plans")
    r.raise_for_status()
    plans = r.json()["plans"]
    assert plans == PLANS
    assert [p["id"] for p in plans] == ["personal", "business", "teams"]
    keys = {"id", "name", "description", "price_monthly_sgd", "price_yearly_sgd",
            "features", "limits", "featured", "available"}
    for p in plans:
        assert set(p) == keys and p["features"]
        assert set(p["limits"]) == {"businesses", "documents"}
    personal, business, teams = plans
    assert personal["price_monthly_sgd"] == 0 and personal["available"]
    assert business["featured"] and business["available"]
    assert (business["price_monthly_sgd"], business["price_yearly_sgd"]) == (29, 290)
    assert teams["price_monthly_sgd"] is None and not teams["available"]
    assert teams["limits"] == {"businesses": None, "documents": None}


async def test_billing_status_unconfigured(client, ctx):
    await ctx.db.kv_set("plan", "personal")
    r = await client.get("/api/billing/status")
    r.raise_for_status()
    body = r.json()
    assert body["plan"] == "personal"
    assert set(body["usage"]) == {"conversations", "messages", "documents", "businesses"}
    assert all(isinstance(v, int) for v in body["usage"].values())
    assert body["usage"]["conversations"] == len((await client.get("/api/conversations")).json())
    assert body["limits"] == PLANS[0]["limits"]
    assert body["checkout_available"] is False


async def test_checkout_503_when_unconfigured(client):
    r = await client.post("/api/billing/checkout",
                          json={"plan_id": "business", "interval": "monthly"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Checkout is not configured yet"


async def test_checkout_with_stripe_configured(client, ctx, monkeypatch):
    monkeypatch.setattr(ctx.settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(ctx.settings, "stripe_price_ids",
                        json.dumps({"business:monthly": "price_m"}))
    captured = {}

    async def fake_session(settings, plan_id, interval, price_id):
        captured.update(plan_id=plan_id, interval=interval, price_id=price_id)
        return "https://checkout.stripe.com/c/pay/cs_test_123"

    monkeypatch.setattr("app.api.billing.create_checkout_session", fake_session)
    assert (await client.get("/api/billing/status")).json()["checkout_available"] is True

    r = await client.post("/api/billing/checkout",
                          json={"plan_id": "business", "interval": "monthly"})
    r.raise_for_status()
    assert r.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_123"}
    assert captured == {"plan_id": "business", "interval": "monthly", "price_id": "price_m"}
    assert (await client.post("/api/billing/checkout", json={
        "plan_id": "business", "interval": "yearly"})).status_code == 503  # unmapped
    assert (await client.post("/api/billing/checkout", json={
        "plan_id": "teams", "interval": "monthly"})).status_code == 503
    assert (await client.post("/api/billing/checkout", json={
        "plan_id": "personal", "interval": "monthly"})).status_code == 400  # free
    assert (await client.post("/api/billing/checkout", json={
        "plan_id": "enterprise", "interval": "monthly"})).status_code == 404


async def test_waitlist_stores_and_validates(client, ctx):
    r = await client.post("/api/billing/waitlist",
                          json={"email": "Owner@Example.com", "plan_id": "teams"})
    assert r.status_code == 201 and r.json() == {"ok": True}
    r = await client.post("/api/billing/waitlist",
                          json={"email": "owner@example.com", "plan_id": "teams"})
    assert r.status_code == 201  # idempotent
    rows = [(e["email"], e["plan_id"]) for e in await ctx.db.waitlist_entries()]
    assert rows.count(("owner@example.com", "teams")) == 1
    for bad in ("not-an-email", "a@b", "@example.com", "a b@example.com"):
        r = await client.post("/api/billing/waitlist", json={"email": bad, "plan_id": "teams"})
        assert r.status_code == 422, bad
    r = await client.post("/api/billing/waitlist",
                          json={"email": "a@b.co", "plan_id": "enterprise"})
    assert r.status_code == 400


async def test_webhook_sets_plan(client, ctx, monkeypatch):
    event = {"type": "checkout.session.completed",
             "data": {"object": {"metadata": {"plan_id": "business"}}}}
    assert (await client.post("/api/billing/webhook", json=event)).status_code == 503

    monkeypatch.setattr(ctx.settings, "stripe_secret_key", "sk_test_123")
    try:
        r = await client.post("/api/billing/webhook", json=event)  # no secret: unverified
        assert r.status_code == 200 and r.json() == {"received": True}
        assert await ctx.db.kv_get("plan") == "business"
        status = (await client.get("/api/billing/status")).json()
        assert status["plan"] == "business" and status["limits"] == PLANS[1]["limits"]

        # an unrelated event, or an unknown plan, leaves the plan alone
        other = {"type": "invoice.paid", "data": {"object": {}}}
        assert (await client.post("/api/billing/webhook", json=other)).status_code == 200
        unknown = {"type": "checkout.session.completed",
                   "data": {"object": {"metadata": {"plan_id": "enterprise"}}}}
        assert (await client.post("/api/billing/webhook", json=unknown)).status_code == 200
        assert await ctx.db.kv_get("plan") == "business"

        # with a signing secret, signatures are enforced
        monkeypatch.setattr(ctx.settings, "stripe_webhook_secret", "whsec_test")
        payload = json.dumps({"type": "checkout.session.completed",
                              "data": {"object": {"metadata": {"plan_id": "personal"}}}})
        headers = {"content-type": "application/json", "stripe-signature": "t=1,v1=bad"}
        assert (await client.post("/api/billing/webhook", content=payload,
                                  headers=headers)).status_code == 400
        assert await ctx.db.kv_get("plan") == "business"
        t = int(time.time())
        sig = hmac.new(b"whsec_test", f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
        headers["stripe-signature"] = f"t={t},v1={sig}"
        r = await client.post("/api/billing/webhook", content=payload, headers=headers)
        assert r.status_code == 200, r.text
        assert await ctx.db.kv_get("plan") == "personal"
    finally:
        await ctx.db.kv_set("plan", "personal")


def test_effective_limit_rules():
    from app.billing import effective_limit

    assert effective_limit(1, 0) == 1          # plan governs
    assert effective_limit(None, 0) is None    # unlimited plan, no cap
    assert effective_limit(None, 5) == 5       # operator ceiling on an unlimited plan
    assert effective_limit(3, 2) == 2          # ceiling tighter than the plan
    assert effective_limit(3, 10) == 3         # ceiling looser than the plan


async def test_meta_and_done_share_message_id_and_attachments_persist(client):
    content = b"LEASE\n\nThe tenant pays a deposit of two months rent, refundable at expiry."
    r = await client.post("/api/documents", files={"file": ("lease.txt", content, "text/plain")})
    r.raise_for_status()
    did = r.json()["id"]
    await wait_ready(client, did)
    events = await chat(client, message="what does my lease say about the deposit",
                        doc_ids=[did])
    meta = by_event(events, "meta")[0]
    done = by_event(events, "done")[0]
    assert meta["message_id"] == done["message_id"]
    conv = (await client.get(f"/api/conversations/{meta['conversation_id']}")).json()
    user_turn = next(m for m in conv["messages"] if m["role"] == "user")
    assert user_turn["meta"]["attachments"] == [{"id": did, "filename": "lease.txt"}]
    assert conv["messages"][-1]["id"] == done["message_id"]
    assert (await client.delete(f"/api/documents/{did}")).status_code == 204
    await delete_conversation(client, meta["conversation_id"])


async def test_search_scoped_by_business(client, ctx):
    r = await client.post("/api/businesses", json={"name": "Scope Test"})
    r.raise_for_status()
    bid = r.json()["id"]
    r = await client.post("/api/documents", data={"business_id": bid},
                          files={"file": ("policy.txt",
                                          b"Staff policy: part-time staff accrue annual leave pro rata.",
                                          "text/plain")})
    r.raise_for_status()
    await wait_ready(client, r.json()["id"])
    r = await client.post("/api/search", json={"query": "part-time annual leave pro rata",
                                               "business_id": bid})
    assert any(x["collection"] == "user_docs" for x in r.json()["results"])
    assert (await client.post("/api/search", json={"query": "x", "business_id": "nope"})).status_code == 404
    assert (await client.delete(f"/api/businesses/{bid}")).status_code == 204

import logging

from fastapi import APIRouter, HTTPException, Request

from app.billing import (
    DEFAULT_PLAN_ID,
    PLANS,
    create_checkout_session,
    get_plan,
    parse_webhook,
    plan_from_checkout_event,
    price_ids,
    stripe_configured,
)
from app.schemas import CheckoutRequest, WaitlistRequest

router = APIRouter(tags=["billing"])
log = logging.getLogger(__name__)

_NOT_CONFIGURED = "Checkout is not configured yet"


@router.get("/billing/plans")
async def plans():
    return {"plans": PLANS}


@router.get("/billing/status")
async def status(request: Request):
    ctx = request.app.state.ctx
    plan = get_plan(await ctx.db.kv_get("plan")) or get_plan(DEFAULT_PLAN_ID)
    return {
        "plan": plan["id"],
        "usage": await ctx.db.usage_counts(ctx.settings.user_id),
        "limits": plan["limits"],
        "checkout_available": stripe_configured(ctx.settings),
    }


@router.post("/billing/checkout")
async def checkout(req: CheckoutRequest, request: Request):
    ctx = request.app.state.ctx
    settings = ctx.settings
    if not stripe_configured(settings):
        raise HTTPException(503, _NOT_CONFIGURED)
    plan = get_plan(req.plan_id)
    if not plan:
        raise HTTPException(404, "unknown plan")
    if not plan["price_monthly_sgd"] and plan["available"]:
        raise HTTPException(400, f"The {plan['name']} plan is free; no checkout needed")
    price_id = price_ids(settings).get(f"{plan['id']}:{req.interval}")
    if not price_id:  # covers teams (talk to us) and any unmapped interval
        raise HTTPException(503, _NOT_CONFIGURED)
    try:
        url = await create_checkout_session(settings, plan["id"], req.interval, price_id)
    except Exception as exc:
        log.exception("stripe checkout session failed")
        raise HTTPException(502, f"Stripe checkout failed: {exc}") from exc
    return {"url": url}


@router.post("/billing/waitlist", status_code=201)
async def waitlist(req: WaitlistRequest, request: Request):
    ctx = request.app.state.ctx
    if not get_plan(req.plan_id):
        raise HTTPException(400, "unknown plan")
    await ctx.db.add_waitlist(req.email, req.plan_id)
    return {"ok": True}


@router.post("/billing/webhook")
async def webhook(request: Request):
    """Stripe → `checkout.session.completed` activates `metadata.plan_id`."""
    ctx = request.app.state.ctx
    settings = ctx.settings
    if not settings.stripe_secret_key and not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhooks are not configured")
    payload = await request.body()
    try:
        event = parse_webhook(settings, payload, request.headers.get("stripe-signature"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    plan_id = plan_from_checkout_event(event)
    if plan_id:
        await ctx.db.kv_set("plan", plan_id)
        log.info("billing: plan set to %s via Stripe webhook", plan_id)
    elif event.get("type") == "checkout.session.completed":
        log.warning("billing: checkout completed without a known metadata.plan_id")
    return {"received": True}

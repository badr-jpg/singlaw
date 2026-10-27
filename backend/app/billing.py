"""Plans and the optional Stripe glue.

Plans are code, not data: prices are placeholders pending the owner's pricing
decision and change with a one-line edit here (DECISIONS.md #22). The active
plan is the kv row `plan` (default "personal"). Stripe is entirely optional —
without STRIPE_SECRET_KEY + STRIPE_PRICE_IDS checkout answers 503 and the UI
offers the waitlist instead.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import Settings

log = logging.getLogger(__name__)

DEFAULT_PLAN_ID = "personal"

PLANS: list[dict[str, Any]] = [
    {
        "id": "personal",
        "name": "Personal",
        "description": "Cited answers on Singapore law for one person, with your own documents.",
        "price_monthly_sgd": 0,
        "price_yearly_sgd": 0,
        "features": [
            "Streaming answers whose citations resolve to the actual provision or judgment",
            "Source explorer: Acts, subsidiary legislation, judgments and practice directions",
            "Provision history and citing-judgments views, with repealed/overruled warnings",
            "Retrieval inspector showing why each source was ranked",
            "Upload up to 10 of your own documents and ask about them",
            "1 business workspace",
        ],
        "limits": {"businesses": 1, "documents": 10},
        "featured": False,
        "available": True,
    },
    {
        "id": "business",
        "name": "Business",
        "description": "Workspaces for each business you run, with its documents and context.",
        "price_monthly_sgd": 29,
        "price_yearly_sgd": 290,
        "features": [
            "Everything in Personal",
            "Up to 3 business workspaces, each with its own documents",
            "Your business profile applied as context to every answer in that workspace",
            "Upload up to 100 documents: contracts, policies, staff handbooks",
            "Priority support",
        ],
        "limits": {"businesses": 3, "documents": 100},
        "featured": True,
        "available": True,
    },
    {
        "id": "teams",
        "name": "Teams",
        "description": "For firms and teams that need custom limits and deployment — talk to us.",
        "price_monthly_sgd": None,
        "price_yearly_sgd": None,
        "features": [
            "Everything in Business",
            "Custom business and document limits",
            "Self-hosted deployment: retrieval models and corpus run on your own machines",
            "Dedicated onboarding and support",
        ],
        "limits": {"businesses": None, "documents": None},
        "featured": False,
        "available": False,
    },
]


def get_plan(plan_id: str | None) -> dict[str, Any] | None:
    return next((p for p in PLANS if p["id"] == plan_id), None)


async def active_plan(db: Any) -> dict[str, Any]:
    """The plan in force: kv `plan`, defaulting to the free Personal plan."""
    return get_plan(await db.kv_get("plan")) or get_plan(DEFAULT_PLAN_ID)  # type: ignore[return-value]


def effective_limit(plan_limit: int | None, operator_cap: int) -> int | None:
    """The plan governs; a positive operator cap is an additional hard ceiling.
    None means unlimited."""
    if operator_cap > 0:
        return operator_cap if plan_limit is None else min(plan_limit, operator_cap)
    return plan_limit


def price_ids(settings: Settings) -> dict[str, str]:
    """STRIPE_PRICE_IDS parsed: {"business:monthly": "price_…", …}."""
    if not settings.stripe_price_ids:
        return {}
    try:
        data = json.loads(settings.stripe_price_ids)
    except ValueError:
        log.warning("STRIPE_PRICE_IDS is not valid JSON; checkout disabled")
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def stripe_configured(settings: Settings) -> bool:
    return bool(settings.stripe_secret_key and price_ids(settings))


async def create_checkout_session(
    settings: Settings, plan_id: str, interval: str, price_id: str,
) -> str:
    """Create a Stripe Checkout Session (subscription) and return its URL.
    `metadata.plan_id` is what the webhook reads back on completion."""
    import stripe  # imported lazily: only needed when billing is configured

    base = settings.public_base_url.rstrip("/")
    client = stripe.StripeClient(settings.stripe_secret_key)
    session = await asyncio.to_thread(client.checkout.sessions.create, {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base}/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/billing?checkout=cancelled",
        "metadata": {"plan_id": plan_id, "interval": interval},
        "subscription_data": {"metadata": {"plan_id": plan_id, "interval": interval}},
    })
    return session.url


def parse_webhook(settings: Settings, payload: bytes, sig_header: str | None) -> Any:
    """Return the event (a mapping). Verifies the Stripe signature when
    STRIPE_WEBHOOK_SECRET is set; raises ValueError on a bad payload/signature."""
    if settings.stripe_webhook_secret:
        import stripe

        try:  # verifies t=/v1= header against the raw body (and its age)
            stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret)
        except stripe.SignatureVerificationError as exc:
            raise ValueError("invalid Stripe signature") from exc
    else:
        log.warning("STRIPE_WEBHOOK_SECRET unset: accepting an unverified webhook event")
    # Parse the raw body ourselves: stripe's Event type is not a mapping in
    # recent SDK versions, and the JSON is all the handler needs.
    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise ValueError("invalid JSON payload") from exc
    if not isinstance(event, dict):
        raise ValueError("invalid event payload")
    return event


def plan_from_checkout_event(event: Any) -> str | None:
    """`metadata.plan_id` of a checkout.session.completed event, if it names a plan."""
    if event.get("type") != "checkout.session.completed":
        return None
    obj = (event.get("data") or {}).get("object") or {}
    plan_id = (obj.get("metadata") or {}).get("plan_id")
    return plan_id if get_plan(plan_id) else None

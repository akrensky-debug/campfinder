"""Stripe checkout and webhook endpoints for Pro plan upgrades."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from campfinder.config import get_settings
from campfinder.database import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


class CheckoutRequest(BaseModel):
    camp_id: str
    email: str


@router.post("/stripe/checkout")
async def create_checkout_session(req: CheckoutRequest) -> dict:
    """Create a Stripe Checkout session for the Pro plan."""
    settings = get_settings()

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    try:
        import stripe  # type: ignore
        stripe.api_key = settings.stripe_secret_key
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")

    supabase = get_supabase()

    # Confirm camp_ownership record exists for this camp+email
    ownership = (
        supabase.table("camp_ownership")
        .select("id, plan")
        .eq("camp_id", req.camp_id)
        .eq("email", req.email)
        .maybe_single()
        .execute()
    )

    if not ownership.data:
        raise HTTPException(status_code=404, detail="No ownership record found. Complete the claim flow first.")

    if ownership.data.get("plan") == "pro":
        raise HTTPException(status_code=400, detail="Already on Pro plan.")

    # Get camp name for display
    camp = (
        supabase.table("camps")
        .select("name")
        .eq("id", req.camp_id)
        .maybe_single()
        .execute()
    )
    camp_name = camp.data["name"] if camp.data else "your camp"

    success_url = f"{settings.frontend_url}/operators/claim/success?camp_id={req.camp_id}&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{settings.frontend_url}/operators/claim?camp_id={req.camp_id}"

    session_params: dict = {
        "mode": "subscription",
        "customer_email": req.email,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "camp_id": req.camp_id,
            "ownership_id": ownership.data["id"],
        },
        "line_items": [
            {
                "price": settings.stripe_pro_price_id,
                "quantity": 1,
            }
        ] if settings.stripe_pro_price_id else [],
    }

    # If no price ID configured, use ad-hoc price for testing
    if not settings.stripe_pro_price_id:
        session_params["line_items"] = [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"CampFinder Pro — {camp_name}",
                        "description": "Priority ranking · Verified badge · Session management · AI discoverability",
                    },
                    "unit_amount": 14900,
                    "recurring": {"interval": "year"},
                },
                "quantity": 1,
            }
        ]

    session = stripe.checkout.Session.create(**session_params)

    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
) -> dict:
    """Handle Stripe webhook events."""
    settings = get_settings()

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    try:
        import stripe  # type: ignore
        stripe.api_key = settings.stripe_secret_key
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")

    body = await request.body()

    if settings.stripe_webhook_secret and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(
                body, stripe_signature, settings.stripe_webhook_secret
            )
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    else:
        # No webhook secret configured — parse raw body (dev only)
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type") if isinstance(event, dict) else event.type

    if event_type == "checkout.session.completed":
        session_obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
        metadata = session_obj.get("metadata", {}) if isinstance(session_obj, dict) else session_obj.metadata
        ownership_id = metadata.get("ownership_id") if metadata else None
        camp_id = metadata.get("camp_id") if metadata else None

        if ownership_id:
            supabase = get_supabase()
            supabase.table("camp_ownership").update({
                "plan": "pro",
                "plan_started_at": "now()",
                "stripe_customer_id": (
                    session_obj.get("customer") if isinstance(session_obj, dict)
                    else session_obj.customer
                ),
            }).eq("id", ownership_id).execute()

            # Also mark the camp as verified
            if camp_id:
                supabase.table("camps").update({
                    "verification_status": "verified",
                }).eq("id", camp_id).execute()

            logger.info("Upgraded ownership %s to Pro", ownership_id)

    return {"received": True}

"""
Billing, Subscription, and Payment Router.
Integrates Razorpay orders, HMAC-SHA256 signature verification, webhook deduplication,
and credit account ledger inspection.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.organization import OrganizationMembership
from app.models.billing import (
    Plan, Subscription, CreditAccount, CreditLedgerEntry, Payment, PaymentStatus
)
from app.schemas.billing import (
    PlanSchema, SubscriptionSchema, CreditAccountSchema,
    CreditLedgerItem, RazorpayOrderCreate, RazorpayPaymentVerify, TopUpCreate
)
from app.api.deps import get_current_user, get_current_membership
from app.services.payment_service import PaymentService
from app.services.credit_engine import CreditEngine
from app.config import settings

router = APIRouter(prefix="/billing", tags=["Billing & Payments"])


@router.get("/plans", response_model=List[PlanSchema])
def list_plans(db: Session = Depends(get_db)):
    """Public/authenticated endpoint listing all active subscription plans."""
    PaymentService.seed_plans(db)
    return db.query(Plan).filter(Plan.is_active == True).all()


@router.get("/account", response_model=CreditAccountSchema)
def get_credit_account(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Returns credit balance, reserved hold, lifetime metrics, and INR value."""
    account = CreditEngine.get_or_create_account(db, membership.organization_id)
    available = max(0.0, account.balance - account.reserved_balance)
    return CreditAccountSchema(
        balance=round(account.balance, 2),
        reserved_balance=round(account.reserved_balance, 2),
        available_balance=round(available, 2),
        lifetime_granted=round(account.lifetime_granted, 2),
        lifetime_consumed=round(account.lifetime_consumed, 2),
        value_inr=round(account.balance * settings.CREDIT_VALUE_INR, 2),
        updated_at=account.updated_at
    )


@router.get("/subscription", response_model=SubscriptionSchema)
def get_active_subscription(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Returns organization's active subscription tier and billing cycle."""
    sub = db.query(Subscription).filter(Subscription.organization_id == membership.organization_id).first()
    if not sub:
        # Default to Free
        free_plan = PaymentService.get_plan_by_tier(db, "FREE")
        if not free_plan:
            PaymentService.seed_plans(db)
            free_plan = PaymentService.get_plan_by_tier(db, "FREE")
        sub = PaymentService.activate_subscription(
            db, membership.organization_id, "order_free_default", "pay_free_default", "FREE"
        )

    return SubscriptionSchema(
        id=sub.id,
        organization_id=sub.organization_id,
        plan_tier=sub.plan.tier.value,
        plan_name=sub.plan.name,
        status=sub.status.value,
        billing_period=sub.billing_period,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end
    )


@router.get("/ledger", response_model=List[CreditLedgerItem])
def get_credit_ledger(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Returns immutable credit ledger entries for auditability."""
    account = CreditEngine.get_or_create_account(db, membership.organization_id)
    entries = db.query(CreditLedgerEntry).filter(
        CreditLedgerEntry.account_id == account.id
    ).order_by(CreditLedgerEntry.created_at.desc()).limit(100).all()
    return entries


@router.post("/checkout")
def create_checkout_order(
    data: RazorpayOrderCreate,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """
    Creates a server-side Razorpay payment order for plan upgrades.
    Amount is strictly calculated on the server.
    """
    return PaymentService.create_order(
        db=db,
        organization_id=membership.organization_id,
        plan_tier=data.plan_tier,
        billing_period=data.billing_period
    )


@router.post("/top-up-order")
def create_top_up_order(
    data: TopUpCreate,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Creates a payment order for purchasing additional AI credits."""
    return PaymentService.create_top_up_order(
        db=db,
        organization_id=membership.organization_id,
        credits_amount=data.credits_amount
    )


@router.post("/verify")
def verify_payment_and_activate(
    data: RazorpayPaymentVerify,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """
    Cryptographic verification endpoint:
    Verifies Razorpay HMAC signature. Never activates plan on client status alone.
    """
    is_valid = PaymentService.verify_payment_signature(
        razorpay_order_id=data.razorpay_order_id,
        razorpay_payment_id=data.razorpay_payment_id,
        razorpay_signature=data.razorpay_signature
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed: Invalid cryptographic signature"
        )

    # If this was a top-up
    if data.top_up_credits:
        CreditEngine.top_up_credits(
            db=db,
            organization_id=membership.organization_id,
            credits=data.top_up_credits,
            reference_id=data.razorpay_payment_id,
            description=f"Purchased {data.top_up_credits} Top-Up Credits"
        )
        return {"status": "SUCCESS", "message": f"Successfully added {data.top_up_credits} credits!"}

    # Otherwise plan subscription activation
    if not data.plan_tier:
        raise HTTPException(status_code=400, detail="Plan tier is required for subscription activation")

    sub = PaymentService.activate_subscription(
        db=db,
        organization_id=membership.organization_id,
        razorpay_order_id=data.razorpay_order_id,
        razorpay_payment_id=data.razorpay_payment_id,
        plan_tier=data.plan_tier,
        billing_period=data.billing_period or "monthly"
    )

    return {
        "status": "SUCCESS",
        "message": f"Plan upgraded to {sub.plan.name}!",
        "plan_tier": sub.plan.tier.value,
        "credits_granted": sub.plan.included_credits_monthly
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Idempotent webhook receiver for Razorpay payment events.
    Verifies X-Razorpay-Signature using raw payload bytes.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not PaymentService.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("event")
    payload = event.get("payload", {})
    payment_entity = payload.get("payment", {}).get("entity", {})

    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")

    if event_type == "payment.captured" and order_id:
        payment = db.query(Payment).filter(Payment.razorpay_order_id == order_id).first()
        if payment and payment.status != PaymentStatus.CAPTURED:
            payment.status = PaymentStatus.CAPTURED
            payment.razorpay_payment_id = payment_id
            db.commit()

    return {"status": "received"}


@router.post("/cancel")
def cancel_subscription(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Marks subscription to cancel at the end of the billing period without deleting data."""
    sub = db.query(Subscription).filter(Subscription.organization_id == membership.organization_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")

    sub.cancel_at_period_end = True
    db.commit()
    return {"message": "Subscription set to cancel at end of billing cycle"}

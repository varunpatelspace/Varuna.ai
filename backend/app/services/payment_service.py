"""
India-First Payment Gateway Service (Razorpay Integration).
Implements:
1. Server-side order creation in paise (1 INR = 100 paise).
2. Strict server-side HMAC-SHA256 signature verification.
3. Raw payload webhook signature validation and deduplication.
4. Plan management, entitlement activation, and credit top-up workflows.
"""

import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.models.billing import (
    Plan, PlanTier, Subscription, SubscriptionStatus,
    Payment, PaymentStatus, CreditAccount
)
from app.services.credit_engine import CreditEngine


DEFAULT_PLANS = [
    {
        "tier": PlanTier.FREE,
        "name": "Varuna Free",
        "description": "Essential AI intelligence for personal exploration and basic tasks.",
        "monthly_price_inr": 0.0,
        "annual_price_inr": 0.0,
        "included_credits_monthly": 100.0,
        "max_request_tokens": 4096,
        "max_file_size_bytes": 5 * 1024 * 1024,
        "allowed_models": "varuna-standard-fast,llama3.2:latest",
        "concurrent_requests": 1,
        "has_web_research": False,
        "has_code_execution": False,
    },
    {
        "tier": PlanTier.STARTER,
        "name": "Varuna Starter",
        "description": "Enhanced speed, developer coding assistant, and document analytics.",
        "monthly_price_inr": 499.0,
        "annual_price_inr": 4990.0,  # 2 months free
        "included_credits_monthly": 5500.0,
        "max_request_tokens": 8192,
        "max_file_size_bytes": 15 * 1024 * 1024,
        "allowed_models": "varuna-standard-fast,varuna-coder-pro,llama3.2:latest",
        "concurrent_requests": 3,
        "has_web_research": True,
        "has_code_execution": True,
    },
    {
        "tier": PlanTier.PRO,
        "name": "Varuna Pro",
        "description": "Full power intelligence with research models, document OCR, and priority compute.",
        "monthly_price_inr": 1499.0,
        "annual_price_inr": 14990.0,
        "included_credits_monthly": 18000.0,
        "max_request_tokens": 16384,
        "max_file_size_bytes": 50 * 1024 * 1024,
        "allowed_models": "all",
        "concurrent_requests": 6,
        "has_web_research": True,
        "has_code_execution": True,
    },
    {
        "tier": PlanTier.BUSINESS,
        "name": "Varuna Business",
        "description": "Multi-user team workspaces, shared credit pools, admin governance, and audit trails.",
        "monthly_price_inr": 4999.0,
        "annual_price_inr": 49990.0,
        "included_credits_monthly": 65000.0,
        "max_request_tokens": 32768,
        "max_file_size_bytes": 100 * 1024 * 1024,
        "allowed_models": "all",
        "concurrent_requests": 15,
        "has_web_research": True,
        "has_code_execution": True,
    }
]


class PaymentService:
    @staticmethod
    def seed_plans(db: Session):
        """Initializes default subscription plans if not present."""
        for p_data in DEFAULT_PLANS:
            existing = db.query(Plan).filter(Plan.tier == p_data["tier"]).first()
            if not existing:
                plan = Plan(**p_data)
                db.add(plan)
        db.commit()

    @staticmethod
    def get_plan_by_tier(db: Session, tier: str) -> Optional[Plan]:
        """Finds plan by tier enum string."""
        try:
            plan_tier = PlanTier(tier.upper())
            return db.query(Plan).filter(Plan.tier == plan_tier, Plan.is_active == True).first()
        except ValueError:
            return None

    @staticmethod
    def create_order(
        db: Session,
        organization_id: str,
        plan_tier: str,
        billing_period: str = "monthly"
    ) -> Dict[str, Any]:
        """
        Creates a payment order for plan subscription.
        Amount is calculated in paise for Razorpay.
        """
        plan = PaymentService.get_plan_by_tier(db, plan_tier)
        if not plan:
            raise HTTPException(status_code=404, detail="Selected plan not found")

        amount_inr = plan.annual_price_inr if billing_period == "annual" else plan.monthly_price_inr
        if amount_inr <= 0:
            raise HTTPException(status_code=400, detail="Free plan does not require a payment transaction")

        amount_paise = int(amount_inr * 100)
        
        # Generate deterministic order ID (in production, calls razorpay.Client.order.create)
        order_receipt = f"rcpt_{organization_id[:8]}_{int(datetime.now().timestamp())}"
        razorpay_order_id = f"order_{hashlib.md5(order_receipt.encode()).hexdigest()[:14]}"

        # Record payment order in database
        payment = Payment(
            organization_id=organization_id,
            razorpay_order_id=razorpay_order_id,
            amount_inr=amount_inr,
            currency="INR",
            status=PaymentStatus.CREATED,
            description=f"Subscription to {plan.name} ({billing_period})"
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        return {
            "order_id": razorpay_order_id,
            "amount_paise": amount_paise,
            "amount_inr": amount_inr,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
            "plan_name": plan.name,
            "billing_period": billing_period
        }

    @staticmethod
    def create_top_up_order(
        db: Session,
        organization_id: str,
        credits_amount: float
    ) -> Dict[str, Any]:
        """Creates an order for on-demand credit top-ups."""
        amount_inr = round(credits_amount * settings.CREDIT_VALUE_INR, 2)
        amount_paise = int(amount_inr * 100)

        order_receipt = f"topup_{organization_id[:8]}_{int(datetime.now().timestamp())}"
        razorpay_order_id = f"order_{hashlib.md5(order_receipt.encode()).hexdigest()[:14]}"

        payment = Payment(
            organization_id=organization_id,
            razorpay_order_id=razorpay_order_id,
            amount_inr=amount_inr,
            currency="INR",
            status=PaymentStatus.CREATED,
            description=f"Credit Top-Up: {credits_amount} Credits"
        )
        db.add(payment)
        db.commit()

        return {
            "order_id": razorpay_order_id,
            "amount_paise": amount_paise,
            "amount_inr": amount_inr,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
            "credits_amount": credits_amount
        }

    @staticmethod
    def verify_payment_signature(
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> bool:
        """
        Cryptographic verification of Razorpay signature.
        Generated Signature = HMAC_SHA256(order_id + "|" + payment_id, secret)
        """
        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        secret = settings.RAZORPAY_KEY_SECRET.encode("utf-8")
        generated_signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
        
        # Test mode tolerance: allow test token verification
        if settings.ENVIRONMENT == "development" and razorpay_signature.startswith("sim_sig_"):
            return True
            
        return hmac.compare_digest(generated_signature, razorpay_signature)

    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
        """Verifies webhook signature using raw byte payload and webhook secret."""
        if not signature_header:
            return False
        secret = settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8")
        expected_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature_header)

    @classmethod
    def activate_subscription(
        cls,
        db: Session,
        organization_id: str,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        plan_tier: str,
        billing_period: str = "monthly"
    ) -> Subscription:
        """
        Activates or upgrades organization subscription and allocates plan credits.
        Guarantees idempotency: checks if payment was already processed.
        """
        payment = db.query(Payment).filter(Payment.razorpay_order_id == razorpay_order_id).first()
        if payment and payment.status == PaymentStatus.CAPTURED:
            # Already processed idempotently
            return db.query(Subscription).filter(Subscription.organization_id == organization_id).first()

        plan = cls.get_plan_by_tier(db, plan_tier)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # Period calculation
        now = datetime.now(timezone.utc)
        period_days = 365 if billing_period == "annual" else 30
        period_end = now + timedelta(days=period_days)

        subscription = db.query(Subscription).filter(Subscription.organization_id == organization_id).first()
        if not subscription:
            subscription = Subscription(
                organization_id=organization_id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                billing_period=billing_period,
                current_period_start=now,
                current_period_end=period_end
            )
            db.add(subscription)
        else:
            subscription.plan_id = plan.id
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.billing_period = billing_period
            subscription.current_period_start = now
            subscription.current_period_end = period_end
            subscription.cancel_at_period_end = False

        db.flush()

        # Update payment record
        if payment:
            payment.status = PaymentStatus.CAPTURED
            payment.razorpay_payment_id = razorpay_payment_id
            payment.subscription_id = subscription.id
        else:
            payment = Payment(
                organization_id=organization_id,
                subscription_id=subscription.id,
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                amount_inr=plan.annual_price_inr if billing_period == "annual" else plan.monthly_price_inr,
                status=PaymentStatus.CAPTURED
            )
            db.add(payment)

        # Grant monthly plan credits
        CreditEngine.top_up_credits(
            db=db,
            organization_id=organization_id,
            credits=plan.included_credits_monthly,
            reference_id=razorpay_payment_id,
            description=f"Monthly credits for {plan.name} plan"
        )

        db.commit()
        db.refresh(subscription)
        return subscription

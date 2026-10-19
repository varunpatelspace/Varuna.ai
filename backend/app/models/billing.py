"""
Billing, Subscription, Credit Account, Ledger, and Usage Accounting Models.
Enforces non-negative balances, atomic double-entry bookkeeping, and transaction audit trails.
"""

import enum
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Text, CheckConstraint, Index
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.user import generate_uuid, utc_now


class PlanTier(str, enum.Enum):
    FREE = "FREE"
    STARTER = "STARTER"
    PRO = "PRO"
    BUSINESS = "BUSINESS"
    ENTERPRISE = "ENTERPRISE"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    TRIALING = "TRIALING"
    EXPIRED = "EXPIRED"


class LedgerEntryType(str, enum.Enum):
    GRANT = "GRANT"                # Monthly quota allocation or sign-up credit
    RESERVATION = "RESERVATION"    # Pre-request credit hold
    SETTLEMENT = "SETTLEMENT"      # Actual token usage finalized
    REFUND = "REFUND"              # Unused reservation released or failed request refunded
    TOP_UP = "TOP_UP"              # User purchased extra credit pack


class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Plan(Base):
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tier = Column(SQLEnum(PlanTier), unique=True, index=True, nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    monthly_price_inr = Column(Float, nullable=False)  # ₹0, ₹499, ₹1499, ₹4999
    annual_price_inr = Column(Float, nullable=False)   # Discounted annual price
    included_credits_monthly = Column(Float, nullable=False)
    max_request_tokens = Column(Integer, default=4096, nullable=False)
    max_file_size_bytes = Column(Integer, default=10 * 1024 * 1024, nullable=False)
    allowed_models = Column(Text, default="all", nullable=False)  # Comma-separated or JSON list
    concurrent_requests = Column(Integer, default=2, nullable=False)
    has_web_research = Column(Boolean, default=False, nullable=False)
    has_code_execution = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=False)
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    billing_period = Column(String(16), default="monthly", nullable=False)  # monthly or annual
    current_period_start = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    razorpay_subscription_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="chk_balance_non_negative"),
        CheckConstraint("reserved_balance >= 0", name="chk_reserved_non_negative"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    reserved_balance = Column(Float, default=0.0, nullable=False)
    lifetime_granted = Column(Float, default=0.0, nullable=False)
    lifetime_consumed = Column(Float, default=0.0, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organization = relationship("Organization", back_populates="credit_account")
    ledger_entries = relationship("CreditLedgerEntry", back_populates="account", cascade="all, delete-orphan")


class CreditLedgerEntry(Base):
    __tablename__ = "credit_ledger_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    account_id = Column(String(36), ForeignKey("credit_accounts.id", ondelete="CASCADE"), index=True, nullable=False)
    entry_type = Column(SQLEnum(LedgerEntryType), nullable=False)
    amount = Column(Float, nullable=False)  # Positive for grant/top-up/refund; negative for settlement
    balance_after = Column(Float, nullable=False)
    reference_id = Column(String(128), index=True, nullable=True)  # request_id, payment_id, or subscription_id
    description = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    account = relationship("CreditAccount", back_populates="ledger_entries")


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("idx_org_created", "organization_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conversation_id = Column(String(36), nullable=True)
    request_id = Column(String(64), unique=True, index=True, nullable=False)
    provider = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cached_tokens = Column(Integer, default=0, nullable=False)
    provider_cost_usd = Column(Float, default=0.0, nullable=False)
    credits_deducted = Column(Float, default=0.0, nullable=False)
    status = Column(String(32), default="SUCCESS", nullable=False)  # SUCCESS, FAILED, TIMEOUT
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    razorpay_order_id = Column(String(128), unique=True, index=True, nullable=False)
    razorpay_payment_id = Column(String(128), unique=True, index=True, nullable=True)
    amount_inr = Column(Float, nullable=False)
    currency = Column(String(8), default="INR", nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.CREATED, nullable=False)
    idempotency_key = Column(String(128), unique=True, index=True, nullable=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    subscription = relationship("Subscription", back_populates="payments")

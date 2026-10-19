"""
Pydantic schemas for Billing, Plans, Subscriptions, Razorpay Payments, and Credit Accounting.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


class PlanSchema(BaseModel):
    id: str
    tier: str
    name: str
    description: str
    monthly_price_inr: float
    annual_price_inr: float
    included_credits_monthly: float
    max_request_tokens: int
    max_file_size_bytes: int
    allowed_models: str
    concurrent_requests: int
    has_web_research: bool
    has_code_execution: bool

    model_config = ConfigDict(from_attributes=True)


class SubscriptionSchema(BaseModel):
    id: str
    organization_id: str
    plan_tier: str
    plan_name: str
    status: str
    billing_period: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool

    model_config = ConfigDict(from_attributes=True)


class CreditAccountSchema(BaseModel):
    balance: float
    reserved_balance: float
    available_balance: float
    lifetime_granted: float
    lifetime_consumed: float
    value_inr: float  # Balance converted to INR equivalent
    updated_at: datetime


class CreditLedgerItem(BaseModel):
    id: str
    entry_type: str
    amount: float
    balance_after: float
    reference_id: Optional[str] = None
    description: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RazorpayOrderCreate(BaseModel):
    plan_tier: str
    billing_period: str = "monthly"  # monthly or annual


class TopUpCreate(BaseModel):
    credits_amount: float = Field(..., ge=100, le=100000, description="Amount of credits to purchase (min 100)")


class RazorpayPaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_tier: Optional[str] = None
    billing_period: Optional[str] = "monthly"
    top_up_credits: Optional[float] = None

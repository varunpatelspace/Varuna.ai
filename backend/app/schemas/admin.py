"""
Pydantic schemas for Platform Owner Administration and Analytics.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class ModelConfigSchema(BaseModel):
    id: str
    provider: str
    model_id: str
    display_name: str
    description: Optional[str] = None
    input_rate_usd_per_1k: float
    output_rate_usd_per_1k: float
    credit_multiplier: float
    context_window: int
    max_output_tokens: int
    is_active: bool
    is_fallback_eligible: bool
    tier_required: str

    model_config = ConfigDict(from_attributes=True)


class ModelConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    input_rate_usd_per_1k: Optional[float] = None
    output_rate_usd_per_1k: Optional[float] = None
    credit_multiplier: Optional[float] = None
    is_active: Optional[bool] = None
    tier_required: Optional[str] = None


class PlatformStats(BaseModel):
    total_users: int
    total_organizations: int
    active_subscriptions: int
    total_credits_consumed: float
    estimated_provider_cost_usd: float
    estimated_revenue_inr: float
    estimated_gross_margin_percent: float
    active_models_count: int
    global_kill_switch_active: bool

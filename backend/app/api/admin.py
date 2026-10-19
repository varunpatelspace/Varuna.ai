"""
Platform Owner Administration Router.
Restricted to Platform Administrators.
Monitors operational gross margins, AI costs, provider health, model pricing,
and emergency kill switches.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import Subscription, SubscriptionStatus, UsageRecord, Payment, PaymentStatus
from app.models.ai_models import ModelConfiguration
from app.models.audit import AuditLog
from app.schemas.admin import ModelConfigSchema, ModelConfigUpdate, PlatformStats
from app.api.deps import require_platform_admin
from app.services.ai_gateway import AIGateway
from app.config import settings

router = APIRouter(prefix="/admin", tags=["Platform Administration"])


@router.get("/stats", response_model=PlatformStats)
def get_platform_analytics(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """
    Computes real-time SaaS platform health, financial metrics, and gross margin.
    """
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_orgs = db.query(func.count(Organization.id)).scalar() or 0
    active_subs = db.query(func.count(Subscription.id)).filter(Subscription.status == SubscriptionStatus.ACTIVE).scalar() or 0

    # Usage aggregates
    total_credits = db.query(func.sum(UsageRecord.credits_deducted)).scalar() or 0.0
    provider_cost_usd = db.query(func.sum(UsageRecord.provider_cost_usd)).scalar() or 0.0

    # Payment aggregates
    revenue_inr = db.query(func.sum(Payment.amount_inr)).filter(Payment.status == PaymentStatus.CAPTURED).scalar() or 0.0

    # Gross Margin calculation
    revenue_usd = revenue_inr / 83.0 if revenue_inr > 0 else 0.0
    if revenue_usd > 0:
        gross_margin_percent = round(((revenue_usd - provider_cost_usd) / revenue_usd) * 100, 2)
    else:
        gross_margin_percent = 85.0  # Projected base margin on prepaid credit economics

    active_models = db.query(func.count(ModelConfiguration.id)).filter(ModelConfiguration.is_active == True).scalar() or 0

    return PlatformStats(
        total_users=total_users,
        total_organizations=total_orgs,
        active_subscriptions=active_subs,
        total_credits_consumed=round(total_credits, 2),
        estimated_provider_cost_usd=round(provider_cost_usd, 4),
        estimated_revenue_inr=round(revenue_inr, 2),
        estimated_gross_margin_percent=gross_margin_percent,
        active_models_count=active_models,
        global_kill_switch_active=settings.GLOBAL_AI_KILL_SWITCH
    )


@router.get("/models", response_model=List[ModelConfigSchema])
def list_all_models(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Lists all models and their cost/multiplier configurations."""
    AIGateway.seed_default_models(db)
    return db.query(ModelConfiguration).all()


@router.put("/models/{model_id}", response_model=ModelConfigSchema)
def update_model_configuration(
    model_id: str,
    data: ModelConfigUpdate,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Updates pricing rates, multiplier, or active state for a model."""
    model = db.query(ModelConfiguration).filter(ModelConfiguration.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model configuration not found")

    if data.display_name is not None:
        model.display_name = data.display_name
    if data.input_rate_usd_per_1k is not None:
        model.input_rate_usd_per_1k = data.input_rate_usd_per_1k
    if data.output_rate_usd_per_1k is not None:
        model.output_rate_usd_per_1k = data.output_rate_usd_per_1k
    if data.credit_multiplier is not None:
        model.credit_multiplier = data.credit_multiplier
    if data.is_active is not None:
        model.is_active = data.is_active
    if data.tier_required is not None:
        model.tier_required = data.tier_required

    db.commit()
    db.refresh(model)
    return model


@router.post("/kill-switch")
def toggle_global_kill_switch(
    active: bool,
    admin: User = Depends(require_platform_admin)
):
    """Emergency control: instantly pauses or resumes all AI generation queries."""
    settings.GLOBAL_AI_KILL_SWITCH = active
    return {
        "status": "UPDATED",
        "global_ai_kill_switch_active": settings.GLOBAL_AI_KILL_SWITCH,
        "message": "Global AI gateway kill-switch has been engaged" if active else "Kill-switch disengaged"
    }


@router.get("/audit-logs")
def get_audit_trail(
    limit: int = 50,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Retrieves security, payment, and administrative audit logs."""
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/users")
def list_registered_users(
    limit: int = 50,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Lists registered users and their roles for administrative oversight."""
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "is_platform_admin": u.is_platform_admin,
            "created_at": u.created_at
        }
        for u in users
    ]

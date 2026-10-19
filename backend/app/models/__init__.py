"""
Centralized model exports for VARUNA AI.
Registers all tables on Base.metadata for migrations and schema creation.
"""

from app.database import Base
from app.models.user import User, UserPreference, SavedMemory, generate_uuid, utc_now
from app.models.organization import Organization, OrganizationMembership, RoleEnum
from app.models.billing import (
    Plan, PlanTier, Subscription, SubscriptionStatus,
    CreditAccount, CreditLedgerEntry, LedgerEntryType,
    UsageRecord, Payment, PaymentStatus
)
from app.models.ai_models import ModelConfiguration, ToolExecution
from app.models.conversation import Conversation, Message, MessageRole, UploadedFile
from app.models.audit import AuditLog

__all__ = [
    "Base",
    "User",
    "UserPreference",
    "SavedMemory",
    "Organization",
    "OrganizationMembership",
    "RoleEnum",
    "Plan",
    "PlanTier",
    "Subscription",
    "SubscriptionStatus",
    "CreditAccount",
    "CreditLedgerEntry",
    "LedgerEntryType",
    "UsageRecord",
    "Payment",
    "PaymentStatus",
    "ModelConfiguration",
    "ToolExecution",
    "Conversation",
    "Message",
    "MessageRole",
    "UploadedFile",
    "AuditLog",
    "generate_uuid",
    "utc_now",
]

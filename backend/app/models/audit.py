"""
Security and System Audit Log Model.
Records all high-impact actions, administrative changes, auth events, and security exceptions.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.user import generate_uuid, utc_now


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_org_action", "organization_id", "action"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)  # AUTH_LOGIN, PLAN_UPGRADE, CREDIT_ADJUSTMENT, MODEL_TOGGLE
    resource_type = Column(String(64), nullable=False)  # User, Subscription, CreditAccount, ModelConfiguration
    resource_id = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)
    metadata_json = Column(Text, nullable=True)  # Sanitized JSON details
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organization = relationship("Organization", back_populates="audit_logs")

"""
Multi-tenant Organization and Role-Based Access Control Models.
"""

import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.user import generate_uuid, utc_now


class RoleEnum(str, enum.Enum):
    PLATFORM_OWNER = "PLATFORM_OWNER"
    ORG_OWNER = "ORG_OWNER"
    ORG_ADMIN = "ORG_ADMIN"
    MEMBER = "MEMBER"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    billing_email = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    memberships = relationship("OrganizationMembership", back_populates="organization", cascade="all, delete-orphan")
    credit_account = relationship("CreditAccount", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="organization", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="organization", cascade="all, delete-orphan")
    files = relationship("UploadedFile", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_org"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SQLEnum(RoleEnum), default=RoleEnum.MEMBER, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")

"""
Database models for Users, Preferences, and Persistent AI Memory.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship

from app.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    avatar_url = Column(String(1024), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=True, nullable=False)
    is_platform_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    memberships = relationship("OrganizationMembership", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    memories = relationship("SavedMemory", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    theme = Column(String(32), default="dark", nullable=False)
    default_model = Column(String(64), default="varuna-standard-fast", nullable=False)
    stream_responses = Column(Boolean, default=True, nullable=False)
    email_notifications = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="preferences")


class SavedMemory(Base):
    __tablename__ = "saved_memories"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    memory_key = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    importance_score = Column(Float, default=1.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="memories")

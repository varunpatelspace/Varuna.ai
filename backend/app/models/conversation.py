"""
Conversation, Message, and Secure Uploaded File Models.
Ensures strict multi-tenant scoping and integrity checks.
"""

import enum
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum, Text, Index
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.user import generate_uuid, utc_now


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("idx_conv_org_user", "organization_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(255), default="New Chat", nullable=False)
    model_id = Column(String(64), default="varuna-standard-fast", nullable=False)
    system_prompt = Column(Text, nullable=True)
    is_archived = Column(String(8), default="false", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organization = relationship("Organization", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_msg_conv_created", "conversation_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
    tool_calls_json = Column(Text, nullable=True)
    tool_call_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String(1024), nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    processing_status = Column(String(32), default="PENDING", nullable=False)  # PENDING, PROCESSED, FAILED
    extracted_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organization = relationship("Organization", back_populates="files")

"""
AI Model Registry and Agent Tool Execution Tracking Models.
Allows runtime dynamic pricing, model enabling/disabling, multipliers, and audit logs for tools.
"""

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text
from app.database import Base
from app.models.user import generate_uuid, utc_now


class ModelConfiguration(Base):
    __tablename__ = "model_configurations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider = Column(String(32), nullable=False)  # openai, anthropic, ollama, simulator
    model_id = Column(String(64), unique=True, index=True, nullable=False)  # gpt-4o, claude-3-5-sonnet, etc.
    display_name = Column(String(128), nullable=False)
    description = Column(String(255), nullable=True)
    input_rate_usd_per_1k = Column(Float, default=0.005, nullable=False)
    output_rate_usd_per_1k = Column(Float, default=0.015, nullable=False)
    credit_multiplier = Column(Float, default=1.0, nullable=False)  # Profit margin & operational multiplier
    context_window = Column(Integer, default=128000, nullable=False)
    max_output_tokens = Column(Integer, default=4096, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_fallback_eligible = Column(Boolean, default=True, nullable=False)
    tier_required = Column(String(32), default="FREE", nullable=False)  # FREE, STARTER, PRO, BUSINESS
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    conversation_id = Column(String(36), index=True, nullable=True)
    tool_name = Column(String(64), nullable=False)
    parameters_json = Column(Text, nullable=False)
    result_json = Column(Text, nullable=True)
    status = Column(String(32), default="SUCCESS", nullable=False)  # SUCCESS, FAILED, TIMEOUT, DENIED
    execution_time_ms = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

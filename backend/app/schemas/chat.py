"""
Pydantic schemas for Chat Conversations, Messages, Streaming, and Tool Calls.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    tokens_used: int = 0
    tool_calls: Optional[List[Dict[str, Any]]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: Optional[str] = "New Chat"
    model_id: Optional[str] = "varuna-standard-fast"
    system_prompt: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    organization_id: str
    user_id: str
    title: str
    model_id: str
    system_prompt: Optional[str] = None
    is_archived: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageItem] = []

    model_config = ConfigDict(from_attributes=True)


class ChatMessageInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=100000)
    model_id: Optional[str] = "varuna-standard-fast"
    enable_tools: bool = True
    enable_web_search: bool = False
    file_ids: Optional[List[str]] = None


class ChatStreamChunk(BaseModel):
    delta: str
    finish_reason: Optional[str] = None
    tokens_used: Optional[int] = None
    credits_charged: Optional[float] = None
    model: Optional[str] = None

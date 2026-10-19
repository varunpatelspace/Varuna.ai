"""
Conversational Workspace and Streaming AI Router.
Implements:
1. Multi-tenant conversation management with strict organizational scoping.
2. Two-phase credit reservation and atomic settlement on streaming completion.
3. Server-Sent Events (SSE) streaming output.
4. Tool dispatch and integration into conversation history.
"""

import json
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.organization import OrganizationMembership
from app.models.conversation import Conversation, Message, MessageRole, UploadedFile
from app.models.billing import UsageRecord, Subscription
from app.schemas.chat import (
    ConversationResponse, ConversationCreate, ChatMessageInput, MessageItem
)
from app.api.deps import get_current_user, get_current_membership
from app.services.ai_gateway import AIGateway
from app.services.credit_engine import CreditEngine
from app.services.agent_executor import AgentExecutor
from app.config import settings

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get("/conversations", response_model=List[ConversationResponse])
def list_conversations(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Lists conversations scoped to current user and organization."""
    conversations = db.query(Conversation).filter(
        Conversation.organization_id == membership.organization_id,
        Conversation.user_id == membership.user_id,
        Conversation.is_archived == "false"
    ).order_by(Conversation.updated_at.desc()).all()
    return conversations


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    data: ConversationCreate,
    user: User = Depends(get_current_user),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Creates a new conversation container."""
    conv = Conversation(
        organization_id=membership.organization_id,
        user_id=user.id,
        title=data.title or "New Chat",
        model_id=data.model_id or "varuna-standard-fast",
        system_prompt=data.system_prompt
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Retrieves conversation and its message history with tenant isolation."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.organization_id == membership.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    return conv


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Archives or permanently deletes conversation."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.organization_id == membership.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db.delete(conv)
    db.commit()
    return {"message": "Conversation deleted successfully"}


@router.post("/conversations/{conversation_id}/messages")
async def send_message_stream(
    conversation_id: str,
    data: ChatMessageInput,
    user: User = Depends(get_current_user),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """
    Primary AI streaming endpoint:
    1. Validates ownership and model access.
    2. Performs pre-request credit reservation.
    3. Handles attached files and agent tools.
    4. Streams response chunks via SSE.
    5. Settles credit usage atomically on stream termination.
    """
    if settings.GLOBAL_AI_KILL_SWITCH:
        raise HTTPException(status_code=503, detail="AI Gateway is temporarily paused for emergency maintenance")

    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.organization_id == membership.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Seed models if needed
    AIGateway.seed_default_models(db)

    # Validate model configuration
    chosen_model_id = data.model_id or conv.model_id
    model_config = AIGateway.get_model_config(db, chosen_model_id)
    if not model_config:
        model_config = AIGateway.get_model_config(db, "varuna-standard-fast")

    # Check Plan Model Entitlements
    sub = db.query(Subscription).filter(Subscription.organization_id == membership.organization_id).first()
    if sub and sub.plan and sub.plan.allowed_models != "all":
        allowed = [m.strip() for m in sub.plan.allowed_models.split(",")]
        if model_config.model_id not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Model '{model_config.display_name}' requires upgrading to a higher plan."
            )

    # Append any uploaded file context to user input
    attached_context = ""
    if data.file_ids:
        for fid in data.file_ids:
            up_file = db.query(UploadedFile).filter(
                UploadedFile.id == fid,
                UploadedFile.organization_id == membership.organization_id
            ).first()
            if up_file and up_file.extracted_text:
                attached_context += f"\n\n[Attached File: {up_file.original_filename}]\n{up_file.extracted_text[:4000]}\n"

    full_user_content = data.content + attached_context

    # Pre-request credit reservation
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    estimated_credits = AIGateway.estimate_reservation_credits(model_config, full_user_content)
    
    CreditEngine.reserve_credits(
        db=db,
        organization_id=membership.organization_id,
        estimated_credits=estimated_credits,
        reference_id=request_id
    )

    # Persist user message
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=data.content
    )
    db.add(user_msg)
    
    # Auto-generate title if this is the first message
    if conv.title == "New Chat":
        conv.title = data.content[:35] + ("..." if len(data.content) > 35 else "")
    db.commit()

    # Build conversation history
    history = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at.asc()).all()
    message_payload = [{"role": m.role.value, "content": m.content} for m in history]

    # Check for agent tool triggers (e.g. calculator or web search)
    tool_injection = ""
    if data.enable_tools:
        lower_content = data.content.lower()
        if any(op in lower_content for op in ["calc", "compute", "sqrt", "+", "*", "/", "math"]):
            # Run calculator if appropriate
            for token in data.content.split():
                if any(char in token for char in ["+", "-", "*", "/", "^"]) and any(c.isdigit() for c in token):
                    calc_res = AgentExecutor.execute_tool("calculator", {"expression": token}, db, conv.id)
                    if calc_res["status"] == "SUCCESS":
                        tool_injection += f"\n[Agent Tool: Calculator result for '{token}' = {calc_res['result']['result']}]\n"

        if data.enable_web_search or "search" in lower_content or "latest" in lower_content:
            web_res = AgentExecutor.execute_tool("web_search", {"query": data.content[:50]}, db, conv.id)
            if web_res["status"] == "SUCCESS":
                tool_injection += f"\n[Agent Tool: Web Research Verified Citations: {json.dumps(web_res['result']['citations'])}]\n"

    if tool_injection:
        message_payload.append({"role": "system", "content": f"Verified tools background context: {tool_injection}"})

    async def event_generator():
        accumulated_text = ""
        actual_credits = estimated_credits
        input_tokens = len(full_user_content) // 4
        output_tokens = 0
        provider_cost = 0.0

        try:
            async for chunk in AIGateway.stream_chat(model_config, message_payload, conv.system_prompt):
                if chunk.get("delta"):
                    accumulated_text += chunk["delta"]
                    yield f"data: {json.dumps({'delta': chunk['delta']})}\n\n"

                if chunk.get("done", False):
                    output_tokens = chunk.get("output_tokens", len(accumulated_text) // 4)
                    input_tokens = chunk.get("input_tokens", input_tokens)
                    provider_cost = chunk.get("provider_cost_usd", 0.0)
                    actual_credits = chunk.get("credits_charged", estimated_credits)
                    break

            # Settle credits atomically
            with Session(db.bind) as settle_db:
                CreditEngine.settle_credits(
                    db=settle_db,
                    organization_id=membership.organization_id,
                    reserved_credits=estimated_credits,
                    actual_credits=actual_credits,
                    reference_id=request_id,
                    description=f"Query {model_config.display_name} ({output_tokens} output tokens)"
                )

                # Persist assistant response
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role=MessageRole.ASSISTANT,
                    content=accumulated_text,
                    tokens_used=input_tokens + output_tokens
                )
                settle_db.add(assistant_msg)

                # Record usage record
                usage = UsageRecord(
                    organization_id=membership.organization_id,
                    user_id=user.id,
                    conversation_id=conv.id,
                    request_id=request_id,
                    provider=model_config.provider,
                    model=model_config.model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    provider_cost_usd=provider_cost,
                    credits_deducted=actual_credits,
                    status="SUCCESS"
                )
                settle_db.add(usage)
                settle_db.commit()

            # Final completion event
            yield f"data: {json.dumps({'done': True, 'tokens': input_tokens + output_tokens, 'credits': actual_credits})}\n\n"

        except Exception as e:
            # Safe refund on failure
            with Session(db.bind) as refund_db:
                CreditEngine.refund_reservation(
                    db=refund_db,
                    organization_id=membership.organization_id,
                    reserved_credits=estimated_credits,
                    reference_id=request_id,
                    reason=f"Streaming error: {str(e)}"
                )
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

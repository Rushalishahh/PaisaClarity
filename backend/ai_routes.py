"""FastAPI routes for PaisaClarity Secure AI Financial Copilot (Phase 9)."""

import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth_dependency import get_current_user
from database import get_db
from models import User, AIConversation, AIMessage
from schemas import (
    AIChatRequest,
    AIChatResponse,
    AIConversationResponse,
    AIConversationDetailResponse,
    AIMessageResponse,
)
from ai.orchestrator import run_copilot_turn

router = APIRouter(prefix="/ai", tags=["ai-copilot"])


@router.post("/chat", response_model=AIChatResponse)
def chat_with_copilot(
    req: AIChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat with the AI Financial Copilot with conversation persistence and secure tool execution."""
    conversation = None
    if req.conversation_id:
        conversation = (
            db.query(AIConversation)
            .filter(
                AIConversation.id == req.conversation_id,
                AIConversation.user_id == current_user.id,
            )
            .first()
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
    else:
        # Create a new conversation with a descriptive title from first prompt
        title_snippet = req.prompt.strip()
        if len(title_snippet) > 40:
            title_snippet = title_snippet[:37] + "..."
        conversation = AIConversation(
            user_id=current_user.id,
            title=title_snippet or "Financial Discussion",
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # Load recent conversation history (last 10 messages for context)
    recent_msgs = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.created_at.desc())
        .limit(10)
        .all()
    )
    # Reverse to chronological order
    history = [{"role": m.role, "content": m.content} for m in reversed(recent_msgs)]

    # Persist user prompt in database
    user_msg = AIMessage(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role="user",
        content=req.prompt,
    )
    db.add(user_msg)
    db.commit()

    # Execute orchestrator
    result = run_copilot_turn(
        user_prompt=req.prompt,
        db=db,
        user=current_user,
        conversation_history=history,
    )

    # Persist assistant's response with tool executions log
    assistant_msg = AIMessage(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role="assistant",
        content=result.content,
        tool_calls=result.tool_executions if result.tool_executions else None,
    )
    db.add(assistant_msg)

    # Update conversation's updated_at timestamp
    conversation.updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()

    return AIChatResponse(
        conversation_id=conversation.id,
        title=conversation.title,
        response=result.content,
        tool_calls=result.tool_executions,
    )


@router.get("/conversations", response_model=list[AIConversationResponse])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all AI conversations for the logged-in user."""
    conversations = (
        db.query(AIConversation)
        .filter(AIConversation.user_id == current_user.id)
        .order_by(AIConversation.updated_at.desc())
        .all()
    )

    results = []
    for c in conversations:
        msg_count = db.query(AIMessage).filter(AIMessage.conversation_id == c.id).count()
        results.append(
            AIConversationResponse(
                id=c.id,
                title=c.title,
                is_archived=c.is_archived,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=msg_count,
            )
        )
    return results


@router.get("/conversations/{conversation_id}", response_model=AIConversationDetailResponse)
def get_conversation_detail(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve full message history for a specific conversation."""
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conv.id)
        .order_by(AIMessage.created_at.asc())
        .all()
    )

    msg_responses = [
        AIMessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            tool_calls=m.tool_calls,
            created_at=m.created_at,
        )
        for m in messages
    ]

    return AIConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        is_archived=conv.is_archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=msg_responses,
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    db.delete(conv)
    db.commit()
    return {"message": "Conversation deleted successfully"}

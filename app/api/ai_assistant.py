from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os
from anthropic import Anthropic

from app.core.database import get_db
from app.models.user import User, UserTier
from app.models.ai_usage import AIUsage
from app.security.auth import get_current_user

router = APIRouter()

# Initialize Anthropic client
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
if anthropic_api_key:
    anthropic_client = Anthropic(api_key=anthropic_api_key)
else:
    anthropic_client = None


# Pricing (per 1M tokens)
PRICING = {
    "claude-3-5-haiku-20241022": {
        "input_cost": 0.80,   # $0.80 per MTok (what WE pay)
        "output_cost": 4.00,  # $4.00 per MTok (what WE pay)
        "input_markup": 3.0,  # 300% markup = $2.40 per MTok (what USER pays)
        "output_markup": 2.5, # 250% markup = $10.00 per MTok (what USER pays)
    }
}

# Tier limits (messages per day)
TIER_LIMITS = {
    UserTier.ANONYMOUS: 0,        # No AI access
    UserTier.BEGINNER: 0,         # No AI access
    UserTier.STUDENT: 10,         # 10 messages/day
    UserTier.PROFESSIONAL: 100,   # 100 messages/day
    UserTier.GOVERNMENT: 500,     # 500 messages/day
    UserTier.ENTERPRISE: 99999,   # Unlimited
    UserTier.CUSTOM: 99999,       # Unlimited
    UserTier.EMPLOYEE: 99999,     # Unlimited
}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[dict] = None  # Can include environment data for better responses


class ChatResponse(BaseModel):
    response: str
    model: str
    tokens_used: dict
    cost: float
    messages_remaining: int


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> tuple[float, float, float]:
    """
    Calculate API cost, user cost, and profit

    Returns: (api_cost, user_cost, profit)
    """
    pricing = PRICING.get(model)
    if not pricing:
        raise ValueError(f"Pricing not configured for model: {model}")

    # What WE pay
    api_cost = (
        (input_tokens / 1_000_000) * pricing["input_cost"] +
        (output_tokens / 1_000_000) * pricing["output_cost"]
    )

    # What USER pays (with markup)
    user_cost = (
        (input_tokens / 1_000_000) * pricing["input_cost"] * pricing["input_markup"] +
        (output_tokens / 1_000_000) * pricing["output_cost"] * pricing["output_markup"]
    )

    profit = user_cost - api_cost

    return (round(api_cost, 6), round(user_cost, 6), round(profit, 6))


def get_daily_message_count(db: Session, user_id: int) -> int:
    """Get number of AI messages user sent today"""
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    return db.query(AIUsage).filter(
        AIUsage.user_id == user_id,
        AIUsage.created_at >= today_start
    ).count()


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Chat with Claude AI Assistant

    **Pricing:**
    - Student: 10 messages/day (included)
    - Professional: 100 messages/day (included)
    - Government: 500 messages/day (included)
    - Enterprise: Unlimited (included)

    **Costs per message:**
    - ~$0.001-0.01 depending on length
    - Billed monthly based on usage
    """

    # Check if API is configured
    if not anthropic_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Assistant is not configured. Please contact support."
        )

    # Check tier access
    tier_limit = TIER_LIMITS.get(current_user.tier, 0)
    if tier_limit == 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "AI Assistant requires a paid plan",
                "message": "Upgrade to Student tier or higher to access the AI Assistant",
                "upgrade_url": "/api/v1/payments/create-checkout-session",
                "pricing": {
                    "student": "$4.99/month - 10 AI messages/day",
                    "professional": "$19.99/month - 100 AI messages/day",
                    "enterprise": "$99.99/month - Unlimited AI messages"
                }
            }
        )

    # Check daily limit
    daily_count = get_daily_message_count(db, current_user.id)
    if daily_count >= tier_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Daily message limit reached",
                "limit": tier_limit,
                "used": daily_count,
                "reset_at": "midnight UTC",
                "upgrade_url": "/api/v1/payments/create-checkout-session"
            }
        )

    # Build system prompt with context
    system_prompt = """You are a helpful AI assistant for MockFactory, a PostgreSQL testing platform.

You help users:
- Create and manage PostgreSQL environments (Standard, Supabase, pgvector, PostGIS)
- Generate SQL queries and mock data
- Understand database concepts
- Troubleshoot connection issues
- Learn about pgvector, PostGIS, and Supabase

Be concise, friendly, and technical. Provide code examples when helpful."""

    # Add context if available
    if request.context:
        environments = request.context.get("environments", [])
        if environments:
            system_prompt += f"\n\nUser has {len(environments)} active environments."

    # Call Claude
    model = "claude-3-5-haiku-20241022"

    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": request.message}
            ]
        )

        # Extract response
        assistant_message = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Calculate costs
        api_cost, user_cost, profit = calculate_cost(input_tokens, output_tokens, model)

        # Log usage
        usage = AIUsage(
            user_id=current_user.id,
            prompt=request.message,
            response=assistant_message,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            api_cost=api_cost,
            user_cost=user_cost,
            profit=profit,
            session_id=request.session_id
        )
        db.add(usage)
        db.commit()

        # Calculate remaining messages
        messages_remaining = tier_limit - (daily_count + 1)

        return ChatResponse(
            response=assistant_message,
            model=model,
            tokens_used={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            },
            cost=user_cost,
            messages_remaining=messages_remaining
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Assistant error: {str(e)}"
        )


@router.get("/usage")
async def get_ai_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get AI assistant usage statistics"""

    tier_limit = TIER_LIMITS.get(current_user.tier, 0)
    daily_count = get_daily_message_count(db, current_user.id)

    # Total usage stats
    from sqlalchemy import func
    total_stats = db.query(
        func.count(AIUsage.id).label("total_messages"),
        func.sum(AIUsage.user_cost).label("total_cost"),
        func.sum(AIUsage.profit).label("total_profit")
    ).filter(AIUsage.user_id == current_user.id).first()

    return {
        "tier": current_user.tier,
        "daily_limit": tier_limit,
        "daily_used": daily_count,
        "daily_remaining": max(0, tier_limit - daily_count),
        "lifetime_messages": total_stats.total_messages or 0,
        "lifetime_cost": round(total_stats.total_cost or 0, 2),
        "has_access": tier_limit > 0
    }

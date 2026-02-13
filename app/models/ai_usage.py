from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class AIUsage(Base):
    """Track AI assistant usage for billing and analytics"""
    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Message details
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    model = Column(String, nullable=False)  # e.g., "claude-3-5-haiku-20241022"

    # Token usage
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)

    # Cost tracking (in USD)
    api_cost = Column(Float, nullable=False)  # What we pay Anthropic/OpenRouter
    user_cost = Column(Float, nullable=False)  # What we charge the user (with markup)
    profit = Column(Float, nullable=False)  # user_cost - api_cost

    # Metadata
    session_id = Column(String, nullable=True)  # Group conversations
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", backref="ai_usage")

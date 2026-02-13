from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class UserTier(str, enum.Enum):
    ANONYMOUS = "anonymous"
    BEGINNER = "beginner"
    STUDENT = "student"
    PROFESSIONAL = "professional"
    GOVERNMENT = "government"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"
    EMPLOYEE = "employee"  # After Dark Systems employees


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # For manual auth
    oauth_user_id = Column(String, unique=True, index=True, nullable=True)  # For SSO (Authentik sub claim)
    is_active = Column(Boolean, default=True)
    is_employee = Column(Boolean, default=False)
    tier = Column(Enum(UserTier), default=UserTier.BEGINNER)

    # Stripe billing
    stripe_customer_id = Column(String, unique=True, index=True, nullable=True)
    stripe_subscription_id = Column(String, unique=True, index=True, nullable=True)
    subscription_status = Column(String, nullable=True)  # active, canceled, past_due, etc.

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    executions = relationship("Execution", back_populates="user")
    usage_records = relationship("UsageRecord", back_populates="user")
    environments = relationship("Environment", back_populates="user")
    api_keys = relationship("APIKey", back_populates="user")

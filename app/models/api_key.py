"""
API Key Model - For programmatic access to environments
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class APIKey(Base):
    """
    API Keys for programmatic access to MockFactory.io

    Users can create API keys to authenticate their applications
    without exposing their account credentials
    """
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)  # User-defined name (e.g., "CI/CD Pipeline")
    key_hash = Column(String, unique=True, nullable=False, index=True)  # SHA256 hash
    prefix = Column(String, nullable=False)  # First 8 chars for identification (e.g., "mf_12345...")
    environment_id = Column(String, ForeignKey("environments.id"), nullable=True)  # Optional environment restriction
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Optional expiration

    # Relationships
    user = relationship("User", back_populates="api_keys")
    environment = relationship("Environment", back_populates="api_keys")

    def is_valid(self) -> bool:
        """Check if API key is valid (active and not expired)"""
        if not self.is_active:
            return False

        if self.expires_at and self.expires_at < datetime.utcnow():
            return False

        return True

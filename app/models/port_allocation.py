"""
Port Allocation Model - Track allocated ports for container port mapping
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class PortAllocation(Base):
    """
    Track port allocations to prevent race conditions

    Ports are allocated from a range (30000-40000) for Docker container
    port mapping. This model ensures atomic allocation without conflicts.
    """
    __tablename__ = "port_allocations"

    id = Column(Integer, primary_key=True, index=True)
    port = Column(Integer, unique=True, nullable=False, index=True)
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)
    service_name = Column(String, nullable=False)  # redis, postgresql, etc.
    allocated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    released_at = Column(DateTime, nullable=True)

    # Relationships
    environment = relationship("Environment")

    # Composite index for fast lookups
    __table_args__ = (
        Index('ix_port_active', 'port', 'is_active'),
    )

    def release(self):
        """Mark port as released"""
        self.is_active = False
        self.released_at = datetime.utcnow()

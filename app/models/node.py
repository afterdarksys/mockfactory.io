from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String

from app.core.database import Base


class NodeAgent(Base):
    __tablename__ = "node_agents"
    id = Column(Integer, primary_key=True)
    node_id = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    credential_hash = Column(String(64), nullable=False)
    certificate_fingerprint = Column(String(128), unique=True)
    capabilities = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    credential_expires_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

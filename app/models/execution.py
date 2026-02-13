from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class Language(str, enum.Enum):
    PYTHON = "python"
    PHP = "php"
    PERL = "perl"
    JAVASCRIPT = "javascript"
    NODE = "node"
    GO = "go"
    SHELL = "shell"
    HTML = "html"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SECURITY_VIOLATION = "security_violation"


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, index=True)  # For anonymous users

    language = Column(Enum(Language), nullable=False)
    code = Column(Text, nullable=False)
    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)

    output = Column(Text)
    error = Column(Text)
    exit_code = Column(Integer)

    execution_time_ms = Column(Float)
    memory_used_mb = Column(Float)

    security_violations = Column(Text)  # JSON array of detected violations
    container_id = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="executions")


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, index=True)

    execution_count = Column(Integer, default=0)
    last_execution = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="usage_records")

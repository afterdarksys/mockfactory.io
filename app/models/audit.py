from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, event

from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    actor_type = Column(String(32), nullable=False, default="user")
    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64))
    resource_id = Column(String(255))
    outcome = Column(String(32), nullable=False)
    request_id = Column(String(128), index=True)
    operation_id = Column(String(128), index=True)
    source_address = Column(String(64))
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


def prevent_audit_mutation(mapper, connection, target):
    raise ValueError("Audit events are append-only")


event.listen(AuditEvent, "before_update", prevent_audit_mutation)
event.listen(AuditEvent, "before_delete", prevent_audit_mutation)

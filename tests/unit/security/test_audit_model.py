import pytest

from app.models.audit import AuditEvent, prevent_audit_mutation


def test_audit_events_default_to_redacted_structured_details():
    event = AuditEvent(action="environment.create", outcome="success")

    assert event.details is None
    assert event.action == "environment.create"


def test_audit_events_cannot_be_updated_or_deleted():
    with pytest.raises(ValueError, match="append-only"):
        prevent_audit_mutation(None, None, AuditEvent())

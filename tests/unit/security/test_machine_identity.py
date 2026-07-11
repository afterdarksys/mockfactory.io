from datetime import datetime, timedelta

from app.security.machine_identity import hash_machine_secret, verify_machine_credential


def test_machine_secret_is_hashed_and_verified():
    stored = hash_machine_secret("node-secret")

    assert stored != "node-secret"
    assert verify_machine_credential("node-secret", stored, None)
    assert not verify_machine_credential("wrong", stored, None)


def test_expired_machine_credential_is_rejected():
    stored = hash_machine_secret("node-secret")

    assert not verify_machine_credential(
        "node-secret", stored, datetime.utcnow() - timedelta(seconds=1)
    )

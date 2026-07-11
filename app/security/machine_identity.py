from datetime import datetime
import hashlib
import hmac

from app.core.config import settings


def hash_machine_secret(secret: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), secret.encode(), hashlib.sha256
    ).hexdigest()


def verify_machine_credential(
    supplied_secret: str, stored_hash: str, expires_at: datetime | None
) -> bool:
    if expires_at and expires_at <= datetime.utcnow():
        return False
    supplied_hash = hash_machine_secret(supplied_secret)
    return hmac.compare_digest(supplied_hash, stored_hash)

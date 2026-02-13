from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import Optional
from app.models.user import User, UserTier
from app.models.execution import UsageRecord
from app.core.config import settings
from datetime import datetime


class UsageTracker:
    """Track and enforce usage limits for code executions"""

    TIER_LIMITS = {
        UserTier.ANONYMOUS: settings.RUNS_ANONYMOUS,
        UserTier.BEGINNER: settings.RUNS_BEGINNER,
        UserTier.STUDENT: settings.RUNS_STUDENT,
        UserTier.PROFESSIONAL: settings.RUNS_PROFESSIONAL,
        UserTier.GOVERNMENT: settings.RUNS_GOVERNMENT,
        UserTier.ENTERPRISE: settings.RUNS_ENTERPRISE,
        UserTier.CUSTOM: settings.RUNS_CUSTOM,
        UserTier.EMPLOYEE: settings.RUNS_EMPLOYEE,
    }

    def __init__(self, db: Session):
        self.db = db

    def check_and_increment(self, user: Optional[User], session_id: str) -> bool:
        """
        Check if user/session can execute code and increment usage.
        Returns True if allowed, raises HTTPException if limit exceeded.
        """

        if user:
            tier = user.tier
            limit = self.TIER_LIMITS.get(tier, settings.RUNS_BEGINNER)

            # Unlimited tiers (-1)
            if limit == -1:
                self._increment_usage(user, session_id)
                return True

            # Check usage
            usage = self._get_usage(user, session_id)
            if usage >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"{tier.value.title()} tier limit reached ({limit} executions/month). Upgrade to continue.",
                    headers={"X-Upgrade-URL": "/pricing"}
                )

            self._increment_usage(user, session_id)
            return True

        else:
            # Anonymous user
            usage = self._get_usage(None, session_id)
            if usage >= settings.RUNS_ANONYMOUS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Anonymous limit reached ({settings.RUNS_ANONYMOUS} executions). Create an account for more runs.",
                    headers={"X-Signup-URL": "/signup"}
                )

            self._increment_usage(None, session_id)
            return True

    def _get_usage(self, user: Optional[User], session_id: str) -> int:
        """Get current usage count"""
        query = self.db.query(UsageRecord)

        if user:
            query = query.filter(UsageRecord.user_id == user.id)
        else:
            query = query.filter(UsageRecord.session_id == session_id)

        record = query.first()
        return record.execution_count if record else 0

    def _increment_usage(self, user: Optional[User], session_id: str):
        """Increment usage count"""
        query = self.db.query(UsageRecord)

        if user:
            query = query.filter(UsageRecord.user_id == user.id)
        else:
            query = query.filter(UsageRecord.session_id == session_id)

        record = query.first()

        if record:
            record.execution_count += 1
            record.last_execution = datetime.utcnow()
        else:
            record = UsageRecord(
                user_id=user.id if user else None,
                session_id=session_id,
                execution_count=1,
                last_execution=datetime.utcnow()
            )
            self.db.add(record)

        self.db.commit()

    def get_remaining_runs(self, user: Optional[User], session_id: str) -> dict:
        """Get remaining runs for user/session"""
        usage = self._get_usage(user, session_id)

        if user:
            tier = user.tier
            limit = self.TIER_LIMITS.get(tier, settings.RUNS_BEGINNER)

            if limit == -1:
                return {
                    "remaining": "unlimited",
                    "tier": tier.value,
                    "subscription_status": user.subscription_status
                }

            remaining = limit - usage
            return {
                "remaining": max(0, remaining),
                "total": limit,
                "used": usage,
                "tier": tier.value,
                "subscription_status": user.subscription_status
            }
        else:
            remaining = settings.RUNS_ANONYMOUS - usage
            return {
                "remaining": max(0, remaining),
                "total": settings.RUNS_ANONYMOUS,
                "used": usage,
                "tier": "anonymous"
            }

    def reset_monthly_usage(self, user: User):
        """Reset monthly usage counter (called by billing system)"""
        record = self.db.query(UsageRecord).filter(UsageRecord.user_id == user.id).first()
        if record:
            record.execution_count = 0
            self.db.commit()

#!/usr/bin/env python3
"""
Grant admin/employee access to a user
Usage: python scripts/grant_admin.py <email>
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User, UserTier
from app.core.config import settings

def grant_admin(email: str):
    """Grant admin/employee access to user"""

    # Create database connection
    engine = create_engine(str(settings.DATABASE_URL))
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check if user exists
        user = db.query(User).filter(User.email == email).first()

        if user:
            # Update existing user
            user.is_employee = True
            user.tier = UserTier.EMPLOYEE
            user.is_active = True
            db.commit()
            print(f"✅ Admin access granted to existing user: {email}")
            print(f"   - Employee: {user.is_employee}")
            print(f"   - Tier: {user.tier}")
            print(f"   - AI Messages: Unlimited")
        else:
            # Create new user
            user = User(
                email=email,
                oauth_user_id=f"sso_{email.split('@')[0]}",
                is_employee=True,
                tier=UserTier.EMPLOYEE,
                is_active=True
            )
            db.add(user)
            db.commit()
            print(f"✅ New admin user created: {email}")
            print(f"   - Employee: True")
            print(f"   - Tier: employee")
            print(f"   - AI Messages: Unlimited")

        print(f"\n🎉 You now have unlimited access to:")
        print(f"   - Environment creation")
        print(f"   - AI Assistant (Claude)")
        print(f"   - All premium features")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/grant_admin.py <email>")
        print("Example: python scripts/grant_admin.py rjc@afterdarksys.com")
        sys.exit(1)

    email = sys.argv[1]
    grant_admin(email)

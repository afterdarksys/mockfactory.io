"""
Background Tasks - Auto-shutdown, billing reconciliation, cleanup
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.models.environment import Environment, EnvironmentStatus
from app.services.environment_provisioner import EnvironmentProvisioner

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """
    Manages background tasks for MockFactory.io

    Tasks:
    - Auto-shutdown inactive environments
    - Billing reconciliation
    - Resource cleanup
    - Usage metrics aggregation
    """

    def __init__(self):
        # Create dedicated database session for background tasks
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db_session = SessionLocal

    async def auto_shutdown_task(self):
        """
        Auto-shutdown environments that have been inactive

        Runs every 5 minutes
        Checks last_activity vs auto_shutdown_hours
        """
        while True:
            try:
                logger.info("Running auto-shutdown check...")
                db = self.db_session()

                # Find all running environments
                running_envs = db.query(Environment).filter(
                    Environment.status == EnvironmentStatus.RUNNING
                ).all()

                shutdown_count = 0
                for env in running_envs:
                    # Skip if auto_shutdown is disabled (0 or None)
                    if not env.auto_shutdown_hours or env.auto_shutdown_hours <= 0:
                        continue

                    # Calculate inactivity duration
                    if env.last_activity:
                        inactive_duration = datetime.utcnow() - env.last_activity
                        shutdown_threshold = timedelta(hours=env.auto_shutdown_hours)

                        if inactive_duration > shutdown_threshold:
                            logger.info(
                                f"Auto-shutting down environment {env.id} "
                                f"(inactive for {inactive_duration.total_seconds() / 3600:.2f} hours)"
                            )

                            try:
                                # Stop the environment
                                provisioner = EnvironmentProvisioner(db)
                                await provisioner.stop(env)

                                # Update status
                                env.status = EnvironmentStatus.STOPPED
                                env.stopped_at = datetime.utcnow()
                                db.commit()

                                shutdown_count += 1
                            except Exception as e:
                                logger.error(f"Failed to auto-shutdown environment {env.id}: {e}")
                                db.rollback()

                logger.info(f"Auto-shutdown check complete. Shutdown {shutdown_count} environments.")
                db.close()

            except Exception as e:
                logger.error(f"Error in auto-shutdown task: {e}")

            # Run every 5 minutes
            await asyncio.sleep(300)

    async def cleanup_destroyed_resources(self):
        """
        Clean up orphaned Docker containers and OCI resources

        Runs every hour
        Looks for containers/buckets not tracked in database
        """
        while True:
            try:
                logger.info("Running resource cleanup...")
                db = self.db_session()

                # TODO: Implement cleanup logic
                # - List all Docker containers with mockfactory prefix
                # - Check if they're tracked in database
                # - Remove orphaned containers
                # - Same for OCI buckets

                db.close()
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

            # Run every hour
            await asyncio.sleep(3600)

    async def billing_reconciliation(self):
        """
        Reconcile usage logs with Stripe billing

        Runs daily at midnight
        Aggregates usage costs per user
        Creates Stripe usage records
        """
        while True:
            try:
                # Calculate time until next midnight UTC
                now = datetime.utcnow()
                tomorrow = now + timedelta(days=1)
                midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
                seconds_until_midnight = (midnight - now).total_seconds()

                # Wait until midnight
                logger.info(f"Waiting {seconds_until_midnight / 3600:.2f} hours until billing reconciliation")
                await asyncio.sleep(seconds_until_midnight)

                logger.info("Running billing reconciliation...")
                db = self.db_session()

                # TODO: Implement billing reconciliation
                # - Aggregate usage logs from last 24 hours
                # - Group by user
                # - Create Stripe usage records
                # - Send billing notifications

                db.close()

            except Exception as e:
                logger.error(f"Error in billing reconciliation: {e}")

    async def start_all_tasks(self):
        """Start all background tasks concurrently"""
        logger.info("Starting background task manager...")

        await asyncio.gather(
            self.auto_shutdown_task(),
            self.cleanup_destroyed_resources(),
            self.billing_reconciliation(),
            return_exceptions=True
        )


# Global instance
background_manager = BackgroundTaskManager()


async def start_background_tasks():
    """Start all background tasks - called from main.py on startup"""
    await background_manager.start_all_tasks()

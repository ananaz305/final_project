import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.user import User
from shared.kafka_client_lib.enums import UserStatus, IdentifierType
from shared.kafka_client_lib.schemas import KafkaVerificationResult, KafkaDeathNotification
from app.db.database import AsyncSessionLocal  # Use factory to create sessions inside the handler

logger = logging.getLogger(__name__)

async def handle_verification_result(message_data: dict):
    """Handles messages from the identity.verification.result topic."""
    try:
        result = KafkaVerificationResult.model_validate(message_data)
        logger.info(f"Processing verification result for userId: {result.userId}, verified: {result.isVerified}")

        async with AsyncSessionLocal() as session:  # Create a new session
            async with session.begin():  # Start a transaction
                # Find the user
                stmt = select(User).where(User.id == result.userId)
                db_result = await session.execute(stmt)
                user = db_result.scalar_one_or_none()

                if not user:
                    logger.warning(f"Verification result for unknown user {result.userId}. Ignoring.")
                    return

                # Update status only if it was pending_verification
                new_status = UserStatus.VERIFIED if result.isVerified else UserStatus.VERIFICATION_FAILED
                if user.status == UserStatus.PENDING_VERIFICATION or user.status == UserStatus.REGISTERED:
                    logger.info(f"Updating user {user.id} status from {user.status} to {new_status}")
                    user.status = new_status
                    session.add(user)
                else:
                    logger.info(f"User {user.id} status is '{user.status}'. No update required based on verification result ({new_status}).")

            # The transaction is automatically committed here upon exiting `async with session.begin()`
            # or rolled back in case of exception

    except Exception as e:
        logger.error(f"Error processing verification result message: {e}", exc_info=True)
        logger.error(f"Original message data: {message_data}")
        # It may be worth adding logic for a Dead Letter Queue

async def handle_death_notification(message_data: dict):
    """Handles messages from the hmrc.death.notification topic."""
    try:
        notification = KafkaDeathNotification.model_validate(message_data)
        logger.info(f"Processing death notification for identifier: {notification.identifierType.value}/{notification.identifierValue} (userId: {notification.userId})")

        async with AsyncSessionLocal() as session:
            async with session.begin():
                user: User | None = None
                # Find the user by ID or identifier
                if notification.userId:
                    stmt = select(User).where(User.id == notification.userId)
                    db_result = await session.execute(stmt)
                    user = db_result.scalar_one_or_none()
                elif notification.identifierType and notification.identifierValue:
                    stmt = select(User).where(
                        User.identifierType == notification.identifierType,
                        User.identifierValue == notification.identifierValue
                    )
                    db_result = await session.execute(stmt)
                    user = db_result.scalar_one_or_none()
                else:
                    logger.error(f"Invalid death notification message: missing userId or identifier. Data: {message_data}")
                    return

                if not user:
                    logger.warning(f"Death notification for unknown user (userId: {notification.userId}, identifier: {notification.identifierType}/{notification.identifierValue}). Ignoring.")
                    return

                # Update status to blocked if it's not already blocked
                if user.status != UserStatus.BLOCKED:
                    logger.info(f"Blocking user {user.id} (status: {user.status}) due to death notification. Reason: {notification.reason or 'N/A'}")
                    user.status = UserStatus.BLOCKED
                    session.add(user)
                    # TODO: Integrate with IAM to revoke tokens/sessions
                else:
                    logger.info(f"User {user.id} is already blocked. Ignoring death notification.")

    except Exception as e:
        logger.error(f"Error processing death notification message: {e}", exc_info=True)
        logger.error(f"Original message data: {message_data}")
        # It may be worth adding logic for a Dead Letter Queue

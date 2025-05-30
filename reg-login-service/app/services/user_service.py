import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Receives the user by email."""
    logger.info(f"Attempting to find user with email: {email}")
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        logger.info(f"Found user {user.id} with email {email}")
    else:
        logger.info(f"No user found with email {email}")

    return user
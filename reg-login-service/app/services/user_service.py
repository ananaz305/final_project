import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.models.user import User, AuthProvider, UserStatus
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Получает пользователя по email."""
    logger.info(f"Attempting to find user with email: {email}")
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        logger.info(f"Found user {user.id} with email {email}")
    else:
        logger.info(f"No user found with email {email}")

    return user

async def create_user_from_google(db: AsyncSession, email: str) -> User:
    """Создает нового пользователя из данных Google OAuth."""
    logger.info(f"Creating new user from Google OAuth with email: {email}")

    new_user = User(
        email=email,
        auth_provider=AuthProvider.GOOGLE,
        status=UserStatus.REGISTERED,
        password=None,  # Пароль не требуется для Google SSO
        identifierType=None,  # Эти поля будут заполнены позже
        identifierValue=None
    )

    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        logger.info(f"Successfully created user {new_user.id} from Google OAuth")
        return new_user
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Database integrity error during Google user creation: {e}")
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error during Google user creation: {e}", exc_info=True)
        raise
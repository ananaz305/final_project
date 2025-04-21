import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_db
from app.models.user import User, UserStatus
from app.core.security import decode_access_token
from app.schemas.user import TokenPayload

logger = logging.getLogger(__name__)

# Схема OAuth2 для получения токена из заголовка
# tokenUrl - это эндпоинт, где клиент МОЖЕТ получить токен (например, /api/v1/auth/login)
# Это используется в основном для документации Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    """
    Зависимость FastAPI: Декодирует токен, проверяет пользователя и возвращает ORM модель User.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)
    if token_data is None:
        logger.warning("Failed to decode token or token is invalid.")
        raise credentials_exception

    if token_data.id is None:
        logger.error("Token payload is missing user ID (id claim).") # Должно быть проверено в decode_access_token
        raise credentials_exception

    # Ищем пользователя в БД
    stmt = select(User).where(User.id == token_data.id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning(f"User with ID {token_data.id} from token not found in DB.")
        raise credentials_exception

    # Проверяем статус пользователя из токена со статусом в БД (на случай изменения)
    if user.status != token_data.status:
        logger.warning(f"User {user.id} status mismatch: token ({token_data.status}) vs DB ({user.status}). Denying access.")
        # Можно обновить токен или просто отказать
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Статус пользователя изменился, требуется повторная аутентификация.",
        )

    if user.status == UserStatus.BLOCKED:
        logger.warning(f"Access denied for blocked user {user.id}.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учетная запись заблокирована.",
        )

    logger.debug(f"Authenticated user: {user.id} ({user.email})")
    return user

# Дополнительная зависимость для проверки, что пользователь верифицирован
# def get_current_verified_user(current_user: User = Depends(get_current_user)) -> User:
#     if current_user.status != UserStatus.VERIFIED:
#         logger.warning(f"Access denied for unverified user {current_user.id}.")
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Требуется верификация пользователя"
#         )
#     return current_user
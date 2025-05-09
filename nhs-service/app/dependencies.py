import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Импортируем функции для работы с токеном (нужно создать security.py или импортировать)
# Пока создадим заглушку здесь же
from jose import JWTError, jwt
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Временная Заглушка Security ---
# (В идеале вынести в app.core.security.py и импортировать)
class TokenPayload(BaseModel):
    sub: Optional[str] = None # email
    id: Optional[str] = None  # user_id (ожидаем UUID в строковом виде)
    status: Optional[str] = None # user_status
    exp: Optional[int] = None

def decode_access_token(token: str) -> Optional[TokenPayload]:
    """Заглушка: Декодирует JWT Access Token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if not payload.get("id"):
            logger.warning("Token missing 'id' claim")
            return None
        token_data = TokenPayload(**payload)
        return token_data
    except JWTError as e:
        logger.warning(f"JWT Error decoding token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None
# --- Конец Заглушки ---


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login") # Указываем на эндпоинт логина в шлюзе

async def get_current_user_token_payload(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    """
    Зависимость FastAPI: Декодирует токен и возвращает его payload.
    Не проверяет пользователя в БД (т.к. ее здесь нет).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)

    if token_data is None or token_data.id is None:
        logger.warning("Failed to decode token or token is invalid/missing ID.")
        raise credentials_exception

    # Здесь можно добавить проверку статуса из токена, если нужно
    # Например, разрешать запись только верифицированным пользователям
    # if token_data.status != "verified":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="User must be verified to perform this action",
    #     )

    logger.debug(f"Authenticated user ID from token: {token_data.id}")
    return token_data
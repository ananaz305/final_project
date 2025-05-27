import logging
# from typing import Optional # Removed Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# Импортируем функции для работы с токеном (нужно создать security.py или импортировать)
# Пока создадим заглушку здесь же
from jose import JWTError, jwt
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Временная Заглушка Security ---
# (В идеале вынести в app.core.security.py и импортировать)
class TokenPayload(BaseModel):
    sub: str | None = None # email
    id: str | None = None  # user_id (ожидаем UUID в строковом виде)
    status: str | None = None # user_status
    exp: int | None = None

# Используем OAuth2PasswordBearer из конфигурации
oauth2_scheme = settings.OAUTH2_SCHEME
bearer_scheme = HTTPBearer()

def decode_access_token(token: str) -> TokenPayload | None:
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

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    """Заглушка: получает текущего пользователя из токена."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_access_token(token)

    if token_data is None or token_data.id is None:
        logger.warning(f"Token data is None or missing ID. Token: {token[:20] if token else 'N/A'}...")
        raise credentials_exception

    # Здесь можно добавить проверку статуса пользователя, если это необходимо для NHS сервиса
    # Например: if token_data.status != "VERIFIED": raise credentials_exception
    logger.info(f"User authenticated for NHS service: id={token_data.id}, sub={token_data.sub}")
    return token_data

# Зависимость для получения ID текущего пользователя (упрощенная)
async def get_current_user_id(current_user: TokenPayload = Depends(get_current_user)) -> str:
    """Извлекает ID пользователя из TokenPayload."""
    if not current_user.id:
        # Эта ситуация не должна произойти, если get_current_user отработал корректно
        logger.error("get_current_user_id called with TokenPayload missing id, this should not happen.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID not found in token after authentication."
        )
    return current_user.id

async def get_current_user_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> TokenPayload:
    token = credentials.credentials
    try:
        # Декодируем JWT; settings.SECRET_KEY и settings.ALGORITHM — конкретные значения из вашего конфига
        payload_dict = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        # Парсим полезную нагрузку в Pydantic-модель
        token_data = TokenPayload(**payload_dict)
    except ExpiredSignatureError:
        # Если срок токена истёк
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла, пожалуйста, авторизуйтесь заново",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (PyJWTError, ValidationError):
        # Неправильный токен или не соответствует схеме TokenPayload
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный или повреждённый токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data
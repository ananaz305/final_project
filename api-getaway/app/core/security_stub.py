import logging
# from typing import Optional # Removed Optional
from pydantic import BaseModel, Field
from jose import JWTError, jwt
import uuid

# Импортируем нужные части из основной конфигурации или определяем заново
# Важно, чтобы SECRET_KEY и ALGORITHM совпадали с reg-login-service
# В идеале, вынести общие настройки в отдельный пакет или использовать переменные окружения
from app.core.config import settings

logger = logging.getLogger(__name__)

# Упрощенная схема Payload, т.к. не все поля могут быть нужны шлюзу для базовой проверки
class TokenPayload(BaseModel):
    sub: str | None = None # email
    id: str | None = None  # user_id
    status: str | None = None # user_status
    # Добавляем поле exp для возможной проверки времени жизни, хотя jose это делает
    exp: int | None = None

def decode_access_token(token: str) -> TokenPayload | None:
    """Заглушка: Декодирует JWT Access Token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        # Простая валидация наличия id
        if not payload.get("id"):
            logger.warning("Token missing 'id' claim")
            return None

        # Используем Pydantic для парсинга и базовой валидации
        token_data = TokenPayload(**payload)
        return token_data
    except JWTError as e:
        logger.warning(f"JWT Error decoding token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None

# --- Функции для использования в зависимостях FastAPI ---
# Это заглушка, в реальном сервисе должна быть полноценная проверка
async def get_current_user_stub(token: str = Depends(settings.OAUTH2_SCHEME)) -> TokenPayload:
    """Заглушка: получает текущего пользователя из токена (без реальной проверки прав)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_access_token(token)
    if token_data is None or token_data.id is None: # Проверяем что id есть
        logger.warning(f"Token data is None or missing ID after decoding token: {token[:20]}... ")
        raise credentials_exception

    # В этой заглушке мы не проверяем статус пользователя или другие права.
    # Просто возвращаем декодированные данные, если токен валиден и содержит id.
    logger.info(f"User authenticated (stub): id={token_data.id}, sub={token_data.sub}")
    return token_data
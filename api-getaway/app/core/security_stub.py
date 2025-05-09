import logging
from typing import Optional
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
    sub: Optional[str] = None # email
    id: Optional[str] = None  # user_id
    status: Optional[str] = None # user_status
    # Добавляем поле exp для возможной проверки времени жизни, хотя jose это делает
    exp: Optional[int] = None

def decode_access_token(token: str) -> Optional[TokenPayload]:
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
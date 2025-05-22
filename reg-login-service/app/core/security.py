import logging
from datetime import datetime, timedelta, timezone
# from typing import Optional # Removed Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError # Добавить импорт

# Предполагается, что TokenPayload импортируется из schemas.user
from app.schemas.user import TokenPayload, UserStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# Конфигурация passlib для хэширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет обычный пароль против хэшированного пароля."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Хэширует пароль."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Создает JWT Access Token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # Добавляем 'iat' (issued at) для полноты
    to_encode.update({"iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> TokenPayload | None:
    """Декодирует JWT Access Token и возвращает payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Pydantic V2 model_validate должен справиться с этим, если поля в TokenPayload обязательные
        token_data = TokenPayload.model_validate(payload) # Используем model_validate
        return token_data
    except JWTError as e:
        logger.warning(f"JWT Error decoding token: {e}") # Логирование ошибки
        return None
    except ValidationError as e: # Обработка ошибок валидации Pydantic
        logger.warning(f"Token payload validation error: {e}")
        return None
    # Убрал ValueError, так как ValidationError покроет проблемы с enum (и другие проблемы типов/отсутствия)
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None
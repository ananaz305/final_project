import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

# Пути импорта должны быть корректны для API Gateway:
# settings будет из api-gateway/app/core/config.py
# TokenPayload и UserStatus будут из api-gateway/app/schemas/user.py (создадим на след. шаге)
from app.schemas.user import TokenPayload, UserStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# Конфигурация passlib для хэширования паролей (не используется в Gateway, но можно оставить)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
# ACCESS_TOKEN_EXPIRE_MINUTES не используется в decode_access_token, но может остаться
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# verify_password и get_password_hash не нужны в Gateway, который только декодирует токен
# Оставляю их на случай, если они понадобятся для чего-то еще, но можно и удалить.
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# create_access_token не нужен в Gateway, Gateway только проверяет токены
# Оставляю на случай редких сценариев (например, Gateway обновляет токен), но обычно это делает auth service
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    to_encode.update({"iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> TokenPayload | None:
    """Декодирует JWT Access Token и возвращает payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload.model_validate(payload)
        return token_data
    except JWTError as e:
        logger.warning(f"JWT Error decoding token: {e}")
        return None
    except ValidationError as e:
        logger.warning(f"Token payload validation error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None 
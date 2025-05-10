// from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.core.config import settings
from app.schemas.user import TokenPayload, UserStatus # Импортируем схему

# Контекст для хеширования паролей (используем bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.ALGORITHM
SECRET_KEY = settings.SECRET_KEY # Ключ для подписи JWT
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет совпадение пароля с хешем."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Генерирует хеш для пароля."""
    return pwd_context.hash(password)

def create_access_token(
        subject: str,  # Теперь это user.id
        user_status: UserStatus,
        expires_delta: Optional[timedelta] = None
) -> str:
    """Создает JWT Access Token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Обновляем payload, используя user.id как sub
    to_encode = {
        "exp": expire,
        "sub": str(subject),  # Теперь это user.id
        "status": user_status.value
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[TokenPayload]:
    """Декодирует JWT Access Token и возвращает payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Проверяем наличие обязательных полей
        token_data = TokenPayload(
            sub=payload.get("sub"),
            id=payload.get("id"),
            status=UserStatus(payload.get("status")) if payload.get("status") else None
        )
        if token_data.sub is None or token_data.id is None or token_data.status is None:
            raise JWTError("Missing claims in token")
        return token_data
    except JWTError as e:
        print(f"JWT Error: {e}") # Логирование ошибки
        return None
    except ValueError:
        print(f"JWT Error: Invalid status value in token")
        return None..
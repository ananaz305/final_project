from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
import logging

# Предполагается, что настройки импортируются из app.core.config
# Если файла config.py нет, его нужно будет создать
# from app.core.config import settings

# --- Заглушки для настроек (если config.py еще не создан) ---
class SettingsPlaceholder:
    SECRET_KEY: str = "your_super_secret_key_here" # Замените!
    ALGORITHM: str = "HS256"

settings = SettingsPlaceholder()
# --- Конец заглушек ---

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login") # URL получения токена, может быть не важен для gateway

def get_current_user_token_payload(token: str = Depends(oauth2_scheme)) -> dict:
    """Декодирует и проверяет JWT токен, возвращает payload."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        # Можно добавить проверку наличия обязательных полей, например, 'sub' (email) или 'user_id'
        email: str | None = payload.get("sub")
        user_id: int | None = payload.get("user_id")
        if email is None or user_id is None:
            logger.warning(f"Token payload missing required fields: {payload}")
            raise credentials_exception
        # Здесь не извлекаем пользователя из БД, только проверяем токен
        # Можно добавить базовую валидацию статуса из токена, если нужно
        # user_status = payload.get("user_status")
        # if user_status == "blocked":
        #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is blocked")

        logger.debug(f"Token validated successfully for user_id: {user_id}")
        return payload # Возвращаем весь payload
    except JWTError as e:
        logger.error(f"JWTError during token decoding: {e}")
        raise credentials_exception
    except ValidationError as e: # На случай, если использовалась Pydantic модель для payload
        logger.error(f"Token payload validation error: {e}")
        raise credentials_exception

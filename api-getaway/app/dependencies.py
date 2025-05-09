from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
import logging
import httpx

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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

class TokenData(BaseModel):
    sub: str | None = None # User ID (UUID)
    # Добавляем поля, которые ожидаются в токене (например, status)
    status: str | None = None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        # Важно: Проверяем наличие и тип ожидаемых полей
        user_id: str | None = payload.get("sub")
        user_status: str | None = payload.get("status")

        if user_id is None or user_status is None:
            logger.error(f"Token payload missing sub or status: {payload}")
            raise credentials_exception

        token_data = TokenData(sub=user_id, status=user_status)

    except JWTError as e:
        logger.error(f"JWTError during token decode: {e}")
        raise credentials_exception
    except ValidationError as e:
        logger.error(f"Token payload validation error: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error during token processing: {e}")
        raise credentials_exception

    # В реальном приложении можно добавить проверку в БД, что пользователь активен и т.д.
    # if user is None:
    #     raise credentials_exception
    return token_data

# Зависимость для проверки авторизации через PDP
async def check_pdp_authorization(
        current_user: TokenData = Depends(get_current_user),
        # Эти параметры нужно будет передавать из конкретного роута
        service_name: str = "default",
        action_name: str = "default"
) -> bool:
    """
    Запрашивает разрешение у PDP сервиса.
    Возвращает True, если разрешено, иначе вызывает HTTPException.
    """
    pdp_url = f"{settings.PDP_SERVICE_URL}/authorize"
    pdp_payload = {
        "user": {
            "status": current_user.status
        },
        "request": {
            "service": service_name,
            "action": action_name
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Sending request to PDP: {pdp_url} with payload: {pdp_payload}")
            response = await client.post(pdp_url, json=pdp_payload, timeout=5.0)
            response.raise_for_status() # Проверка на HTTP ошибки (4xx, 5xx)

            result = response.json()
            logger.info(f"Received response from PDP: {result}")

            if result.get("decision") == "allow":
                return True
            elif result.get("decision") == "deny":
                logger.warning(f"PDP denied access for user {current_user.sub} to {service_name}:{action_name}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied by PDP"
                )
            else:
                logger.error(f"Unexpected PDP response format: {result}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid response from PDP service"
                )

        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error occurred while requesting PDP: {exc.request.url} - {exc.response.status_code} - {exc.response.text}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="PDP service request failed"
            )
        except httpx.RequestError as exc:
            logger.error(f"Request error occurred while requesting PDP: {exc.request.url} - {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="PDP service is unreachable"
            )
        except Exception as e:
            logger.exception(f"An unexpected error occurred during PDP check: {e}") # Используем exception для стектрейса
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during authorization check"
            )

    # Эта строка не должна достигаться при нормальной работе
    return False
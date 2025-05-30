import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from pydantic import ValidationError

from app.schemas.user import TokenPayload, UserStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# passlib configuration for password hashing (not used in Gateway)
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

def decode_access_token(token: str) -> TokenPayload | None:
    """Decodes the JWT Access Token and returns the payload."""
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
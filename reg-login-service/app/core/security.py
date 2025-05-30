import logging
from datetime import datetime, timedelta, timezone
# from typing import Optional # Removed Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError # Added import

# Assumes that TokenPayload is imported from schemas.user
from app.schemas.user import TokenPayload, UserStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# Passlib configuration for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Creates a JWT Access Token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # Add 'iat' (issued at) for completeness
    to_encode.update({"iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> TokenPayload | None:
    """Decodes the JWT Access Token and returns the payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Pydantic V2 model_validate should handle this if all fields in TokenPayload are required
        token_data = TokenPayload.model_validate(payload)  # Use model_validate
        return token_data
    except JWTError as e:
        logger.warning(f"JWT Error decoding token: {e}")  # Log the error
        return None
    except ValidationError as e:  # Handle Pydantic validation errors
        logger.warning(f"Token payload validation error: {e}")
        return None
    # Removed ValueError since ValidationError covers enum issues and other type/missing field problems
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None

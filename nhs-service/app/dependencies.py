import logging
# from typing import Optional # Removed Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import functions for working with the token (you need to create security.py or import it)
# For now, we'll create a placeholder here
from jose import JWTError, jwt
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Temporary Security Stub ---
# (Ideally, move this to app.core.security.py and import it)
class TokenPayload(BaseModel):
    sub: str | None = None  # email
    id: str | None = None  # user_id (expecting UUID as string)
    status: str | None = None  # user_status
    exp: int | None = None

class ExpiredSignatureError(Exception):
    pass

class ValidationError(Exception):
    pass

# Use OAuth2PasswordBearer from the configuration
oauth2_scheme = settings.OAUTH2_SCHEME
bearer_scheme = HTTPBearer()

def decode_access_token(token: str) -> TokenPayload | None:
    """Stub: Decodes JWT Access Token."""
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
    """Stub: retrieves current user from the token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_access_token(token)

    if token_data is None or token_data.id is None:
        logger.warning(f"Token data is None or missing ID. Token: {token[:20] if token else 'N/A'}...")
        raise credentials_exception

    # You can add user status verification here if necessary for the NHS service
    # Example: if token_data.status != "VERIFIED": raise credentials_exception
    logger.info(f"User authenticated for NHS service: id={token_data.id}, sub={token_data.sub}")
    return token_data

# Dependency to get the current user's ID (simplified)
async def get_current_user_id(current_user: TokenPayload = Depends(get_current_user)) -> str:
    """Extracts user ID from TokenPayload."""
    if not current_user.id:
        # This situation should not occur if get_current_user worked correctly
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
        # Decode JWT; settings.SECRET_KEY and settings.ALGORITHM are specific values from your config
        payload_dict = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        # Parse the payload into a Pydantic model
        token_data = TokenPayload(**payload_dict)
    except ExpiredSignatureError:
        # If the token has expired
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (JWTError, ValidationError):
        # Invalid token or does not match the TokenPayload schema
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or corrupted token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data

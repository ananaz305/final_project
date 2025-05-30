import logging
from typing import Optional
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_db
from app.models.user import User, UserStatus
from app.core.security import decode_access_token
from app.schemas.user import TokenPayload

logger = logging.getLogger(__name__)

# OAuth2 scheme for extracting token from the Authorization header
# tokenUrl is the endpoint where a client CAN obtain a token (e.g., /api/v1/auth/login)
# This is mainly used for Swagger UI documentation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    """
    FastAPI dependency: Decodes the token, checks the user, and returns the ORM User model.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)
    if token_data is None:
        logger.warning("Failed to decode token or token is invalid.")
        raise credentials_exception

    # Use token_data.sub and convert to UUID
    try:
        user_id_from_token = uuid.UUID(token_data.sub)
    except ValueError:
        logger.warning(f"Invalid UUID format for 'sub' claim in token: {token_data.sub}")
        raise credentials_exception

    # Pydantic should already ensure the presence of sub in TokenPayload,
    # but just in case, we ensure user_id_from_token is not None after conversion
    # (although UUID() won't return None).
    # A stricter check of token_data.sub for None should be inside decode_access_token via Pydantic

    # Query the user from DB
    stmt = select(User).where(User.id == user_id_from_token)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning(f"User with ID {user_id_from_token} from token not found in DB.")
        raise credentials_exception

    # Compare user status in the token vs DB (in case it changed)
    if user.status != token_data.status:
        logger.warning(f"User {user.id} status mismatch: token ({token_data.status}) vs DB ({user.status}). Denying access.")
        # Optionally refresh the token or just deny access
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User status has changed, re-authentication required.",
        )

    if user.status == UserStatus.BLOCKED:
        logger.warning(f"Access denied for blocked user {user.id}.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked.",
        )

    logger.debug(f"Authenticated user: {user.id} ({user.email})")
    return user

# Optional dependency to ensure the user is verified
# def get_current_verified_user(current_user: User = Depends(get_current_user)) -> User:
#     if current_user.status != UserStatus.VERIFIED:
#         logger.warning(f"Access denied for unverified user {current_user.id}.")
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="User verification is required."
#         )
#     return current_user

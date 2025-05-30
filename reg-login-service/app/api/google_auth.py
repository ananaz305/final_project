import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from google.oauth2 import id_token
from google.auth.transport import requests

from app.db.database import get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.services.user_service import get_user_by_email, create_user_from_google
from app.schemas.user import Token

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/login")
async def google_login():
    """Initiates the Google login process."""
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?client_id={client_id}"
        "&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=email profile"
        "&access_type=offline"
        "&prompt=consent"
    ).format(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    return RedirectResponse(url=google_auth_url)

@router.get("/callback")
async def google_callback(
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    """Handles the callback from Google OAuth."""
    try:
        # Get the authorization code from query parameters
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authorization code not provided"
            )

        # Exchange the code for a token
        token_request = requests.Request()
        id_info = id_token.verify_oauth2_token(
            code,
            token_request,
            settings.GOOGLE_CLIENT_ID
        )

        # Extract email from the token
        email = id_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )

        # Check if user exists
        user = await get_user_by_email(db, email)

        # If the user doesn't exist, create a new one
        if not user:
            user = await create_user_from_google(db, email)

        # Create JWT token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        token_data = {
            "sub": str(user.id),
            "status": user.status.value  # Pass the string value of the Enum
            # Note: if you decide to include email or auth_provider in TokenPayload,
            # add them here, for example:
            # "email": user.email,
            # "auth_provider": user.auth_provider.value
        }
        access_token = create_access_token(
            data=token_data,
            expires_delta=access_token_expires
        )

        # Return the token
        return Token(access_token=access_token, token_type="bearer")

    except ValueError as e:
        logger.error(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    except Exception as e:
        logger.error(f"Unexpected error during Google authentication: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authentication"
        )

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
    """Инициирует процесс входа через Google."""
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
    """Обрабатывает callback от Google OAuth."""
    try:
        # Получаем код авторизации из query параметров
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authorization code not provided"
            )

        # Обмениваем код на токен
        token_request = requests.Request()
        id_info = id_token.verify_oauth2_token(
            code,
            token_request,
            settings.GOOGLE_CLIENT_ID
        )

        # Получаем email из токена
        email = id_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )

        # Проверяем существование пользователя
        user = await get_user_by_email(db, email)

        # Если пользователь не существует, создаем нового
        if not user:
            user = await create_user_from_google(db, email)

        # Создаем JWT токен
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=str(user.id),  # Используем user.id как sub
            user_status=user.status,
            expires_delta=access_token_expires
        )

        # Возвращаем токен
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
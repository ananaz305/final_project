from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
import logging
import httpx

from app.core.config import settings # Importing settings

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

class TokenData(BaseModel):
    sub: str | None = None # User ID (UUID)
    # Adding fields that we expect to receive
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
        # Checking for required fields
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

    # In production, we could check here if user suspended or not allowed to use method
    # if user is None:
    #     raise credentials_exception
    return token_data

# Dependency for verifying authorization via PDP
async def check_pdp_authorization(
        current_user: TokenData = Depends(get_current_user),
        # These parameters will need to be transmitted from a specific router
        service_name: str = "default",
        action_name: str = "default"
) -> bool:
    """
    Requests permission from the PDP service.
    Returns True if allowed, otherwise it causes HttpException.
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
            response.raise_for_status() # Http error checking (4xx, 5xx)

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

    # This line should not be reached during normal operation
    return False
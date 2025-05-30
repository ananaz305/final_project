import logging
import uuid  # Add uuid import
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.user import User  # UserStatus is imported from shared.kafka_client_lib.enums
from shared.kafka_client_lib.enums import UserStatus  # Add UserStatus import
from app.schemas.user import UserCreate, UserResponse, Token, LoginRequest, KafkaVerificationRequest
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from shared.kafka_client_lib.client import send_kafka_message
from app.dependencies import get_current_user  # Dependency to get the current user
from shared.kafka_client_lib.exceptions import KafkaMessageSendError

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Registers a new user."""
    logger.info(f"Attempting to register user with email: {user_in.email}")
    # Check for existing user
    stmt = select(User).where((User.email == user_in.email) |
                              ((User.identifierType == user_in.identifierType) &
                               (User.identifierValue == user_in.identifierValue)))
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.email == user_in.email:
            logger.warning(f"Registration failed: email {user_in.email} already exists.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists",
            )
        else:
            logger.warning(f"Registration failed: identifier {user_in.identifierType.value}/{user_in.identifierValue} already exists.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A user with this {user_in.identifierType.value} already exists",
            )

    # Hashing the password
    hashed_password = get_password_hash(user_in.password)

    # Creating a new user in the DB
    new_user = User(
        email=user_in.email,
        identifierType=user_in.identifierType,
        identifierValue=user_in.identifierValue,
        password=hashed_password,
        phoneNumber=user_in.phoneNumber
        # status defaults to 'pending_verification'
    )
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user)  # Retrieve ID and other default values from DB
        logger.info(f"User {new_user.id} registered successfully with status {new_user.status}.")
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Database integrity error during registration: {e}")
        # This might happen in rare race conditions
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration error. Email or identifier might already be in use.",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error during user creation commit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server error during user creation.",
        )

    # Sending a message to Kafka
    # Generate correlation_id for this verification process
    # In future, if register_user is called as part of a larger request,
    # the correlation_id can be inherited.
    correlation_id = str(uuid.uuid4())
    logger.info(f"Generated correlation_id {correlation_id} for user {new_user.id} registration process.")

    kafka_message = KafkaVerificationRequest(
        userId=str(new_user.id),
        identifierType=new_user.identifierType,
        identifierValue=new_user.identifierValue,
        timestamp=datetime.now().isoformat(),
        correlation_id=correlation_id  # Pass the correlation_id
    )
    try:
        await send_kafka_message(
            settings.IDENTITY_VERIFICATION_REQUEST_TOPIC,
            kafka_message.model_dump()
        )
        logger.info(f"Verification request sent to Kafka for user {new_user.id}, correlation_id: {correlation_id}")
    except KafkaMessageSendError as e:
        # If Kafka send fails, user is still registered.
        # Important: how to handle such cases?
        # 1. Roll back the user registration? (Hard if commit already happened)
        # 2. Log and continue? (User is registered but verification won’t start)
        # 3. Respond to client with error indicating service is unavailable?
        # Current implementation: log and return successful registration.
        # This means verification might require manual intervention or retry later.
        logger.error(f"Failed to send Kafka verification request for user {new_user.id} (correlation_id: {correlation_id}): {e}", exc_info=True)
        # You could add logic here, e.g., set user status to PENDING_SYSTEM_RECOVERY
        # or enqueue a retry job.
        # For MVP, just log it.
        # If Kafka is critical, you could raise an HTTPException:
        # raise HTTPException(
        #     status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        #     detail="Registration successful, but verification service is temporarily unavailable. Please try again later or contact support."
        # )
        pass  # Continue despite Kafka error

    return new_user


@router.post("/login", response_model=Token)
async def login_for_access_token(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticates a user and returns a JWT token."""
    logger.info(f"Login attempt for email: {login_data.email}")
    stmt = select(User).where(User.email == login_data.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password):
        logger.warning(f"Login failed for email: {login_data.email} - Invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == UserStatus.BLOCKED:
        logger.warning(f"Login failed for email: {login_data.email} - Account blocked")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    # Check if the user is verified (if required for login)
    if user.status != UserStatus.VERIFIED:
        logger.warning(f"Login failed for email: {login_data.email} - Account not verified (status: {user.status.value})")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not verified. Please complete the verification process.",
        )

    # Create the token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": str(user.id),  # sub should be the user's ID (UUID string)
        "status": user.status.value  # Pass Enum value for status
        # Note: if you add email or auth_provider to TokenPayload,
        # include them here, e.g.:
        # "email": user.email,
        # "auth_provider": user.auth_provider.value
    }
    access_token = create_access_token(
        data=token_data,
        expires_delta=access_token_expires
    )
    logger.info(f"Login successful for user {user.id} ({user.email}). Token issued.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Returns the profile of the currently authenticated user."""
    # get_current_user already fetched the user from the DB
    logger.info(f"Fetching profile for user {current_user.id}")
    return current_user

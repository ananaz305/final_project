import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserPublic, Token, LoginRequest, KafkaVerificationRequest
from app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token
from app.core.config import settings
from app.kafka.client import send_kafka_message
from app.dependencies import get_current_user # Зависимость для получения текущего пользователя

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Регистрирует нового пользователя."""
    logger.info(f"Attempting to register user with email: {user_in.email}")
    # Проверка на существующего пользователя
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
                detail="Пользователь с таким email уже существует",
            )
        else:
            logger.warning(f"Registration failed: identifier {user_in.identifierType.value}/{user_in.identifierValue} already exists.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Пользователь с таким {user_in.identifierType.value} уже существует",
            )

    # Хеширование пароля
    hashed_password = get_password_hash(user_in.password)

    # Создание пользователя в БД
    new_user = User(
        email=user_in.email,
        identifierType=user_in.identifierType,
        identifierValue=user_in.identifierValue,
        password=hashed_password,
        phoneNumber=user_in.phoneNumber
        # status по умолчанию 'pending_verification'
    )
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user) # Получаем ID и другие значения по умолчанию из БД
        logger.info(f"User {new_user.id} registered successfully with status {new_user.status}.")
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Database integrity error during registration: {e}")
        # Это может произойти в редких случаях гонки запросов
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка регистрации. Email или идентификатор уже могут быть заняты.",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error during user creation commit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка сервера при создании пользователя.",
        )

    # Отправка сообщения в Kafka
    kafka_message = KafkaVerificationRequest(
        userId=new_user.id,
        identifierType=new_user.identifierType,
        identifierValue=new_user.identifierValue,
        timestamp=datetime.now().isoformat()
    )
    await send_kafka_message(
        settings.IDENTITY_VERIFICATION_REQUEST_TOPIC,
        kafka_message.model_dump() # Используем model_dump() для Pydantic v2
    )
    logger.info(f"Verification request sent to Kafka for user {new_user.id}")

    return new_user


@router.post("/login", response_model=Token)
async def login_for_access_token(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Аутентифицирует пользователя и возвращает JWT токен."""
    logger.info(f"Login attempt for email: {login_data.email}")
    stmt = select(User).where(User.email == login_data.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password):
        logger.warning(f"Login failed for email: {login_data.email} - Invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == UserStatus.BLOCKED:
        logger.warning(f"Login failed for email: {login_data.email} - Account blocked")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учетная запись заблокирована",
        )

    # Можно добавить проверку на статус 'verified' если требуется
    # if user.status != UserStatus.VERIFIED:
    #     logger.warning(f"Login failed for email: {login_data.email} - Account not verified")
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Учетная запись не верифицирована",
    #     )

    # Создание токена
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.email,
        user_id=user.id,
        user_status=user.status,
        expires_delta=access_token_expires
    )
    logger.info(f"Login successful for user {user.id} ({user.email}). Token issued.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/profile", response_model=UserPublic)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Возвращает профиль текущего аутентифицированного пользователя."""
    # Зависимость get_current_user уже извлекла пользователя из БД
    logger.info(f"Fetching profile for user {current_user.id}")
    return current_user
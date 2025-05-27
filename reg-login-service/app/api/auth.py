import logging
import uuid # Добавляем импорт uuid
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.user import User # UserStatus будет импортирован из shared.kafka_client_lib.enums
from shared.kafka_client_lib.enums import UserStatus # Добавляем импорт UserStatus
from app.schemas.user import UserCreate, UserResponse, Token, LoginRequest, KafkaVerificationRequest
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from shared.kafka_client_lib.client import send_kafka_message
from app.dependencies import get_current_user # Зависимость для получения текущего пользователя
from shared.kafka_client_lib.exceptions import KafkaMessageSendError

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
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
    # Генерируем correlation_id для этого нового процесса верификации
    # В будущем, если register_user вызывается в рамках более крупного запроса,
    # correlation_id может быть унаследован.
    correlation_id = str(uuid.uuid4())
    logger.info(f"Generated correlation_id {correlation_id} for user {new_user.id} registration process.")

    kafka_message = KafkaVerificationRequest(
        userId=str(new_user.id),
        identifierType=new_user.identifierType,
        identifierValue=new_user.identifierValue,
        timestamp=datetime.now().isoformat(),
        correlation_id=correlation_id # Передаем correlation_id
    )
    try:
        await send_kafka_message(
            settings.IDENTITY_VERIFICATION_REQUEST_TOPIC,
            kafka_message.model_dump()
        )
        logger.info(f"Verification request sent to Kafka for user {new_user.id}, correlation_id: {correlation_id}")
    except KafkaMessageSendError as e:
        # Если отправка в Kafka не удалась, регистрация все равно произошла.
        # Это важный момент: как обрабатывать такие ситуации?
        # 1. Откатить регистрацию пользователя? (Сложно, если коммит уже прошел)
        # 2. Залогировать и продолжить? (Пользователь зарегистрирован, но верификация не начнется)
        # 3. Ответить клиенту ошибкой, что сервис временно недоступен?
        # Текущая реализация: логируем и возвращаем успешный ответ о регистрации.
        # Это означает, что процесс верификации может потребовать ручного вмешательства или повторной попытки позже.
        logger.error(f"Failed to send Kafka verification request for user {new_user.id} (correlation_id: {correlation_id}): {e}", exc_info=True)
        # Можно добавить здесь специфическую логику, например, изменить статус пользователя на PENDING_SYSTEM_RECOVERY
        # или добавить задачу в очередь для повторной отправки.
        # Для MVP просто логируем.
        # Если Kafka критична для процесса, можно было бы выбросить HTTPException:
        # raise HTTPException(
        #     status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        #     detail="Registration successful, but verification service is temporarily unavailable. Please try again later or contact support."
        # )
        pass # Продолжаем, несмотря на ошибку Kafka

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

    # Проверяем, что пользователь верифицирован (если это требуется для входа)
    if user.status != UserStatus.VERIFIED:
        logger.warning(f"Login failed for email: {login_data.email} - Account not verified (status: {user.status.value})")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учетная запись не верифицирована. Пожалуйста, завершите процесс верификации.",
        )

    # Создание токена
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": str(user.id), # sub должен быть ID пользователя (строка UUID)
        "status": user.status.value # Передаем значение Enum для статуса
        # Примечание: если вы решите добавить email или auth_provider в TokenPayload,
        # их нужно будет добавить здесь, например:
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
    """Возвращает профиль текущего аутентифицированного пользователя."""
    # Зависимость get_current_user уже извлекла пользователя из БД
    logger.info(f"Fetching profile for user {current_user.id}")
    return current_user
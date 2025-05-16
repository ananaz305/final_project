import uuid
from pydantic import BaseModel, EmailStr, Field
# from typing import Optional # Removed Optional

# Импортируем Enum типы из модели, чтобы использовать их в схемах
from app.models.user import IdentifierType, UserStatus, AuthProvider

# --- Базовые схемы ---
class UserBase(BaseModel):
    email: EmailStr
    identifierType: IdentifierType | None = None
    identifierValue: str | None = Field(None, min_length=3)
    phoneNumber: str | None = None

# --- Схемы для создания ---
class UserCreate(UserBase):
    password: str | None = Field(None, min_length=8)

# --- Схемы для отображения (возвращаем из API) ---
class UserResponse(UserBase):
    id: uuid.UUID
    status: UserStatus
    auth_provider: AuthProvider # Добавили auth_provider

    class Config:
        orm_mode = True # Устарело в Pydantic V2, заменено на from_attributes = True
        from_attributes = True

# --- Схемы для аутентификации ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str # Обычно это user ID (UUID в нашем случае)
    status: UserStatus # Статус обязателен в нашем JWT
    # id: str | None = None # Поле id дублирует sub, можно убрать если sub это user_id

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# --- Схемы для Kafka сообщений ---
class KafkaVerificationRequest(BaseModel):
    userId: uuid.UUID
    identifierType: IdentifierType
    identifierValue: str
    timestamp: str # ISO format timestamp

class KafkaVerificationResult(BaseModel):
    userId: uuid.UUID
    identifierType: IdentifierType
    isVerified: bool
    timestamp: str
    error: str | None = None

class KafkaDeathNotification(BaseModel):
    identifierType: IdentifierType
    identifierValue: str
    userId: uuid.UUID | None = None # Может прийти, а может и нет
    reason: str | None = None
    timestamp: str

# --- Схемы для Google OAuth ---
class GoogleOAuthCode(BaseModel):
    code: str
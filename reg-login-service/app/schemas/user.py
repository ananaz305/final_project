import uuid
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

# Импортируем Enum типы из модели, чтобы использовать их в схемах
from app.models.user import IdentifierType, UserStatus, AuthProvider

# --- Базовые схемы ---
class UserBase(BaseModel):
    email: EmailStr
    identifierType: Optional[IdentifierType] = None
    identifierValue: Optional[str] = Field(None, min_length=3)
    phoneNumber: Optional[str] = None

# --- Схемы для создания ---
class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=8)

# --- Схемы для чтения (ответа API) ---
class UserPublic(UserBase):
    id: uuid.UUID
    status: UserStatus
    auth_provider: AuthProvider
    # Не включаем password

    class Config:
        from_attributes = True # Позволяет создавать схему из ORM модели

# --- Схемы для аутентификации ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str # Обычно это user ID (UUID в нашем случае)
    status: UserStatus # Статус обязателен в нашем JWT
    # id: Optional[str] = None # Поле id дублирует sub, можно убрать если sub это user_id

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
    error: Optional[str] = None

class KafkaDeathNotification(BaseModel):
    identifierType: IdentifierType
    identifierValue: str
    userId: Optional[uuid.UUID] = None # Может прийти, а может и нет
    reason: Optional[str] = None
    timestamp: str
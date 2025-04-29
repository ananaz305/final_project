import uuid
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

# Импортируем Enum типы из модели, чтобы использовать их в схемах
from app.models.user import IdentifierType, UserStatus

# --- Базовые схемы ---
class UserBase(BaseModel):
    email: EmailStr
    identifierType: IdentifierType
    identifierValue: str = Field(..., min_length=3) # Пример валидации длины
    phoneNumber: Optional[str] = None

# --- Схемы для создания ---
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

# --- Схемы для чтения (ответа API) ---
class UserPublic(UserBase):
    id: uuid.UUID
    status: UserStatus
    # Не включаем password

    class Config:
        from_attributes = True # Позволяет создавать схему из ORM модели

# --- Схемы для аутентификации ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str # Обычно это email или user ID
    # Можно добавить другие поля, например, роли, статус
    id: Optional[str] = None # Добавим ID для удобства
    status: Optional[UserStatus] = None

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
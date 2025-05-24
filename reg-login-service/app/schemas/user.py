import uuid
from pydantic import BaseModel, EmailStr, Field
from typing import Optional # Added Optional
from datetime import datetime

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
    password: str = Field(min_length=8)
    # При регистрации можно передавать NIN или NHS опционально, если они известны
    nin: Optional[str] = None
    nhs_number: Optional[str] = None

# --- Схемы для отображения (возвращаем из API) ---
class UserResponse(UserBase):
    id: uuid.UUID
    status: UserStatus
    auth_provider: AuthProvider
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Замена orm_mode на from_attributes

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

# --- Схемы для Google OAuth ---
class GoogleOAuthCode(BaseModel):
    code: str
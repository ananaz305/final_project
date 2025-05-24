import uuid
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

# Обновляем импорты Enum из общего модуля
from shared.enums import IdentifierType, UserStatus, AuthProvider

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
    created_at: Optional[datetime] = None # Сделаем опциональными, т.к. в User модели их нет
    updated_at: Optional[datetime] = None # Сделаем опциональными, т.к. в User модели их нет

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
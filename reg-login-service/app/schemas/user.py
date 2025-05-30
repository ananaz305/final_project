import uuid
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

# Updated Enum imports from shared module
from shared.kafka_client_lib.enums import IdentifierType, UserStatus, AuthProvider

class KafkaVerificationRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    userId: str
    identifierType: str
    identifierValue: str
    timestamp: str

# --- Base schemas ---
class UserBase(BaseModel):
    email: EmailStr
    identifierType: IdentifierType | None = None
    identifierValue: str | None = Field(None, min_length=3)
    phoneNumber: str | None = None

# --- Schemas for creation ---
class UserCreate(UserBase):
    password: str = Field(min_length=8)
    # During registration, NIN or NHS may be passed optionally if known
    nin: Optional[str] = None
    nhs_number: Optional[str] = None

# --- Schemas for output (returned from API) ---
class UserResponse(UserBase):
    id: uuid.UUID
    status: UserStatus
    auth_provider: AuthProvider
    created_at: Optional[datetime] = None  # Make optional since not in User model
    updated_at: Optional[datetime] = None  # Make optional since not in User model

    class Config:
        from_attributes = True  # Replaces orm_mode with from_attributes

# --- Schemas for authentication ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str  # Typically this is the user ID (UUID in our case)
    status: UserStatus  # Status is required in our JWT
    # id: str | None = None  # Field `id` duplicates `sub`; can be omitted if sub is user_id

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

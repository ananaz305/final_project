import uuid
import enum # Добавляем импорт enum
from pydantic import BaseModel
from typing import Optional

# Копируем IdentifierType сюда временно
class IdentifierType(str, enum.Enum):
    NIN = "NIN"
    NHS = "NHS"

# --- Схемы для Kafka сообщений ---
class KafkaVerificationRequest(BaseModel):
    userId: uuid.UUID
    identifierType: IdentifierType
    identifierValue: str
    timestamp: str # ISO format timestamp
    correlation_id: str

class KafkaVerificationResult(BaseModel):
    userId: uuid.UUID
    identifierType: IdentifierType
    isVerified: bool
    timestamp: str
    error: str | None = None

class KafkaDeathNotification(BaseModel):
    identifierType: IdentifierType
    identifierValue: str
    userId: uuid.UUID | None = None
    reason: str | None = None
    timestamp: str
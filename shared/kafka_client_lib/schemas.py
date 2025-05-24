import uuid
# import enum # Больше не нужен здесь
from pydantic import BaseModel
from typing import Optional

# Импортируем IdentifierType из общего модуля shared.enums
from shared.enums import IdentifierType

# --- Схемы для Kafka сообщений ---
class KafkaVerificationRequest(BaseModel):
    userId: uuid.UUID
    identifierType: IdentifierType
    identifierValue: str
    timestamp: str # ISO format timestamp
    correlation_id: str

class KafkaVerificationResult(BaseModel):
    userId: uuid.UUID
    # identifierType: IdentifierType # Уже есть в KafkaVerificationRequest, но если здесь тоже нужно, оставляем. Обычно по userId идет результат.
    # Если в result приходит identifierType, то оставляем. В коде handlers.py он не используется из result.
    # Уточнение: в текущей версии handlers.py KafkaVerificationResult используется, и там есть identifierType. Оставляем.
    identifierType: IdentifierType # Оставляем, так как используется в KafkaVerificationResult.model_validate(message_data)
    isVerified: bool
    timestamp: str
    error: str | None = None

class KafkaDeathNotification(BaseModel):
    identifierType: IdentifierType
    identifierValue: str
    userId: uuid.UUID | None = None
    reason: str | None = None
    timestamp: str
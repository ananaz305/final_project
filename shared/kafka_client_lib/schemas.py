import uuid
# import enum # No longer needed here
from pydantic import BaseModel
from typing import Optional

# Import IdentifierType from the shared module shared.kafka_client_lib.enums
from .enums import IdentifierType

# --- Schemas for Kafka messages ---
class KafkaVerificationRequest(BaseModel):
    userId: uuid.UUID
    identifierType: IdentifierType
    identifierValue: str
    timestamp: str  # ISO format timestamp
    correlation_id: str

class KafkaVerificationResult(BaseModel):
    userId: uuid.UUID
    # identifierType: IdentifierType # Already present in KafkaVerificationRequest, but if it's needed here too, we keep it.
    # Usually, the result is tied to userId.
    # If identifierType is included in the result, we keep it. It's not used from result in handlers.py.
    # Clarification: in the current version of handlers.py, KafkaVerificationResult is used, and identifierType is present.
    # So we keep it.
    identifierType: IdentifierType  # Keep it, as it's used in KafkaVerificationResult.model_validate(message_data)
    isVerified: bool
    timestamp: str
    error: str | None = None

class KafkaDeathNotification(BaseModel):
    identifierType: IdentifierType
    identifierValue: str
    userId: uuid.UUID | None = None
    reason: str | None = None
    timestamp: str

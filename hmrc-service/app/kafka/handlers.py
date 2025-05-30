import logging
import asyncio
import re
import uuid
from datetime import datetime
from pydantic import BaseModel, ValidationError, ConfigDict

from app.core.config import settings
from shared.kafka_client_lib.client import send_kafka_message

logger = logging.getLogger(__name__)

# Message schemes (similar to NHS-service)
class UserData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    user_id: str

class IdentifierType(str):
    pass

class KafkaVerificationRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    userId: str
    identifierType: str
    identifierValue: str
    timestamp: str

class KafkaVerificationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    userId: str
    identifierType: str
    isVerified: bool
    timestamp: str
    error: str | None = None

class KafkaDeathNotification(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    identifierType: str
    identifierValue: str
    userId: str | None = None # Can be added later
    reason: str | None = None
    timestamp: str

async def handle_nin_verification_request(message_data: dict):
    """Processes verification requests by filtering by type NIN."""
    try:
        request = KafkaVerificationRequest.model_validate(message_data)
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Received verification request for userId: {request.userId}")

        # We process only NIN requests.
        if request.identifierType != "NIN":
            logger.debug(f"[{settings.KAFKA_CLIENT_ID}] Skipping request for type {request.identifierType}")
            return

        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Processing NIN verification for userId: {request.userId}, identifier: {request.identifierValue}")

        # --- Simulating an HMRC API call ---
        is_verified = False
        verification_error = None
        try:
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Simulating HMRC API call for {request.identifierValue}...")
            await asyncio.sleep(1.8) # Simulated delay

            # Simple verification of the NIN format (stub)

            is_verified = True
            if re.match(r"^[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]$", request.identifierValue, re.IGNORECASE):
                is_verified = True
                logger.info(f"[{settings.KAFKA_CLIENT_ID}] HMRC API Stub: Identifier {request.identifierValue} verified.")
            else:
                is_verified = False
                verification_error = "Invalid NIN format (stub check)"
                logger.info(f"[{settings.KAFKA_CLIENT_ID}] HMRC API Stub: Identifier {request.identifierValue} NOT verified.")

        except Exception as api_error:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error during HMRC API simulation for {request.identifierValue}: {api_error}")
            is_verified = False
            verification_error = "HMRC API simulation failed"
        # --- End of the simulation ---

        # Sending the result back to Kafka
        result_message = KafkaVerificationResult(
            userId=request.userId,
            identifierType=request.identifierType,
            isVerified=is_verified,
            timestamp=datetime.now().isoformat(),
            error=verification_error
        )

        await send_kafka_message(
            settings.IDENTITY_VERIFICATION_RESULT_TOPIC,
            result_message.model_dump()
        )
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Verification result sent to Kafka for userId {request.userId}")

    except ValidationError as e:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Validation error processing verification request: {e}")
        logger.error(f"Original message data: {message_data}")
    except Exception as e:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error processing verification request message: {e}", exc_info=True)
        logger.error(f"Original message data: {message_data}")

async def handle_death_notification(message_data: dict):
    pass



async def send_death_notification_event(identifier_type: str, identifier_value: str, reason: str | None = None):
    """Simulates sending a death event to Kafka."""
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Initiating sending death notification for {identifier_type}: {identifier_value}")
    message = KafkaDeathNotification(
        identifierType=IdentifierType(identifier_type), # Converting a string to a type
        identifierValue=identifier_value,
        reason=reason or "Death reported by HMRC (Simulated)",
        timestamp=datetime.now().isoformat()
    )
    await send_kafka_message(
        settings.HMRC_DEATH_NOTIFICATION_TOPIC,
        message.model_dump()
    )
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Death notification sent to Kafka for {identifier_value}")


async def schedule_death_notification_simulation():
    """Runs a background task to simulate a death event."""
    if settings.SIMULATE_DEATH_EVENT:
        delay = settings.SIMULATE_DEATH_DELAY_SECONDS
        nin = settings.SIMULATE_DEATH_NIN
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Scheduling death notification simulation for NIN {nin} in {delay} seconds.")
        await asyncio.sleep(delay)
        await send_death_notification_event("NIN", nin)
    else:
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Death notification simulation is disabled.")
import logging
import asyncio
import re
from datetime import datetime, timedelta
from pydantic import BaseModel, ValidationError
import uuid # Import uuid
import random
from pydantic import BaseModel, ConfigDict


from app.core.config import settings
from shared.kafka_client_lib.client import send_kafka_message
from app.schemas.appointment import (
    AppointmentRequest,
    AppointmentData,
    AppointmentStatus,
    KafkaAppointmentRequest,
    KafkaAppointmentResult # Добавили импорт
)

logger = logging.getLogger(__name__)

# Определим Pydantic схемы для входящих и исходящих сообщений Kafka здесь же
# (В больших проектах их можно вынести в общий schemas модуль)
class IdentifierType(str):
    # Простая строка, т.к. Enum не нужен для сравнения
    pass

class KafkaVerificationRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    userId: uuid.UUID
    identifierType: IdentifierType
    identifierValue: str
    timestamp: str

class KafkaVerificationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    userId: uuid.UUID
    identifierType: IdentifierType
    isVerified: bool
    timestamp: str
    error: str | None = None

async def handle_verification_result(message_data: dict):
    """Обрабатывает сообщения с результатом верификации (например, от reg-login-service)."""
    try:
        # Предполагаем, что формат сообщения соответствует KafkaVerificationResult
        # из reg-login-service/app/schemas/user.py или аналогичной общей схеме
        # Для простоты, используем локально определенную KafkaVerificationResult, но она должна быть совместима.
        result = KafkaVerificationResult.model_validate(message_data)
        logger.info(f"Received identity verification result for userId: {result.userId}, verified: {result.isVerified}")

        if result.isVerified:
            logger.info(f"User {result.userId} successfully verified (identifier: {result.identifierType}). NHS service can proceed.")
            # TODO: Добавить бизнес-логику для NHS-сервиса после успешной верификации
            # Например, обновить статус пользователя в NHS, разрешить доступ к определенным функциям и т.д.
        else:
            logger.warning(f"User {result.userId} verification failed (identifier: {result.identifierType}). Error: {result.error}")
            # TODO: Добавить бизнес-логику для случая неудачной верификации

    except ValidationError as e:
        logger.error(f"Validation error processing verification result: {e}. Message data: {message_data}")
    except Exception as e:
        logger.error(f"Error processing verification result message: {e}. Message data: {message_data}", exc_info=True)

async def handle_nhs_verification_request(message_data: dict):
    """Обрабатывает запросы на верификацию, фильтруя по типу NHS."""
    try:
        request = KafkaVerificationRequest.model_validate(message_data)
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Received verification request for userId: {request.userId}")

        # Обрабатываем только NHS запросы
        if request.identifierType != "NHS":
            logger.debug(f"[{settings.KAFKA_CLIENT_ID}] Skipping request for type {request.identifierType}")
            return

        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Processing NHS verification for userId: {request.userId}, identifier: {request.identifierValue}")

        # --- Имитация вызова NHS API ---
        is_verified = False
        verification_error = None
        try:
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Simulating NHS API call for {request.identifierValue}...")
            await asyncio.sleep(1.5) # Имитация задержки

            # Простая проверка формата NHS номера (заглушка)
            if re.match(r"^NHS\d{9}$", request.identifierValue, re.IGNORECASE):
                is_verified = True
                logger.info(f"[{settings.KAFKA_CLIENT_ID}] NHS API Stub: Identifier {request.identifierValue} verified.")
            else:
                is_verified = False
                verification_error = "Invalid NHS number format (stub check)"
                logger.info(f"[{settings.KAFKA_CLIENT_ID}] NHS API Stub: Identifier {request.identifierValue} NOT verified.")

        except Exception as api_error:
            logger.error(f"[{settings.KAFKA_CLIENT_ID}] Error during NHS API simulation for {request.identifierValue}: {api_error}")
            is_verified = False
            verification_error = "NHS API simulation failed"
        # --- Конец имитации ---

        # Отправка результата обратно в Kafka
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

async def simulate_appointment_processing(appointment_data: KafkaAppointmentRequest):
    """Имитирует обработку записи и отправляет результат в Kafka."""
    try:
        # Validate input data if it comes as dict
        if isinstance(appointment_data, dict):
            appointment_data_model = KafkaAppointmentRequest.model_validate(appointment_data)
        else:
            appointment_data_model = appointment_data # Already a model instance

        processing_time = random.uniform(settings.SIMULATED_PROCESSING_MIN_DELAY, settings.SIMULATED_PROCESSING_MAX_DELAY)
        logger.info(f"Simulating processing for appointment {appointment_data_model.appointment_id} for {processing_time:.2f} seconds...")
        await asyncio.sleep(processing_time)

        # Имитация результата
        possible_statuses = [AppointmentStatus.CONFIRMED, AppointmentStatus.REJECTED]
        final_status = random.choice(possible_statuses)
        confirmation_details = None
        rejection_reason = None
        confirmed_datetime_iso = None

        if final_status == AppointmentStatus.CONFIRMED:
            confirmation_details = f"Confirmed with Dr. Smith, Room {random.randint(100, 500)}"
            # Имитируем подтвержденное время (может немного отличаться от запрошенного)
            confirmed_dt = datetime.fromisoformat(appointment_data_model.requested_datetime) + timedelta(minutes=random.choice([-15, 0, 15, 30]))
            confirmed_datetime_iso = confirmed_dt.isoformat()
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Appointment {appointment_data_model.appointment_id} simulated as CONFIRMED.")
        else:
            rejection_reason = random.choice(["Doctor unavailable", "Slot already booked", "Clinic closed"])
            logger.info(f"[{settings.KAFKA_CLIENT_ID}] Appointment {appointment_data_model.appointment_id} simulated as REJECTED. Reason: {rejection_reason}")

        # Формируем сообщение с результатом
        result_message = KafkaAppointmentResult(
            appointment_id=appointment_data_model.appointment_id,
            user_id=appointment_data_model.user_id,
            status=final_status,
            confirmed_datetime=confirmed_datetime_iso,
            confirmation_details=confirmation_details,
            rejection_reason=rejection_reason,
            timestamp=datetime.now().isoformat()
        )

        # Отправляем результат в Kafka
        await send_kafka_message(
            settings.MEDICAL_APPOINTMENT_RESULT_TOPIC,
            result_message.model_dump()
        )
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Appointment result {appointment_data_model.appointment_id} sent to Kafka topic {settings.MEDICAL_APPOINTMENT_RESULT_TOPIC}")

    except Exception as e:
        logger.error(f"Error during appointment processing simulation for {getattr(appointment_data, 'appointment_id', 'unknown_id')}: {e}", exc_info=True)

async def handle_appointment_result(message_data: dict):
    """(Опционально) Обрабатывает сообщения с результатом записи (просто логирует)."""
    try:
        result = KafkaAppointmentResult.model_validate(message_data)
        logger.info(f"Received processed appointment result via Kafka: ID={result.appointment_id}, Status={result.status}, User={result.user_id}")
        # Здесь можно было бы обновить статус в БД или отправить уведомление пользователю
    except Exception as e:
        logger.error(f"Error processing appointment result message: {e}", exc_info=True)

# TODO: Добавить обработчик для medical.appointment.request, когда будет реализован
# async def handle_appointment_request(message_data: dict):
#    pass

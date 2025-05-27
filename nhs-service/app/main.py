import logging
import logging.config
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any, Dict, Optional

from .core.config import settings
from shared.kafka_client_lib.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    start_kafka_consumer,
    disconnect_kafka_consumers,
    send_kafka_message
)
from shared.kafka_client_lib.exceptions import KafkaConnectionError, KafkaMessageSendError
from .kafka.handlers import (
    handle_verification_result,
    handle_appointment_result,
    simulate_appointment_processing,
    handle_nhs_verification_request
)
# Заглушка для зависимости проверки токена (пока не реализуем)
# from app.dependencies import get_current_verified_user
# Импортируем зависимость и схемы
from .dependencies import get_current_user_token_payload, TokenPayload
from .schemas.appointment import (
    AppointmentRequest,
    AppointmentData,
    AppointmentStatus,
    KafkaAppointmentRequest,
    KafkaAppointmentResult
)
# from app.kafka.consumers import consume_verification_requests # Закомментировано, если consumer запускается отдельно

# Настройка логирования (аналогично reg-login)
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "loggers": {
        "app": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "shared": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "aiokafka": {"handlers": ["console"], "level": "WARNING"},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app.nhs-service")

# Store consumer tasks to manage them
consumer_tasks: List[asyncio.Task] = []
kafka_producer_ready = asyncio.Event() # Если сервис будет что-то отправлять в Kafka
kafka_connection_task: Optional[asyncio.Task] = None

async def connect_kafka_producer_with_event_nhs():
    global kafka_producer_ready
    if not (hasattr(settings, 'KAFKA_BOOTSTRAP_SERVERS') and hasattr(settings, 'KAFKA_CLIENT_ID')):
        logger.critical("NHS: KAFKA_BOOTSTRAP_SERVERS or KAFKA_CLIENT_ID not configured.")
        return
    try:
        logger.info("NHS: Background task: Attempting to connect Kafka producer...")
        await connect_kafka_producer(
            broker_url=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=settings.KAFKA_CLIENT_ID
        )
        kafka_producer_ready.set()
        logger.info("NHS: Background task: Kafka producer connected successfully.")
    except KafkaConnectionError as e:
        logger.error(f"NHS: Background task: Kafka producer connection failed: {e}")
        kafka_producer_ready.clear()
    except Exception as e:
        logger.error(f"NHS: Background task: Unexpected error in Kafka producer connection task: {e}", exc_info=True)
        kafka_producer_ready.clear()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом Kafka producer и consumer tasks."""
    global consumer_tasks, kafka_connection_task, kafka_producer_ready
    logger.info(f"[{settings.PROJECT_NAME}] Starting up via lifespan...")
    kafka_producer_ready.clear()

    # Запуск Kafka Producer (если нужен)
    logger.info("NHS Service: Initiating Kafka producer connection...")
    if hasattr(settings, 'KAFKA_BOOTSTRAP_SERVERS') and hasattr(settings, 'KAFKA_CLIENT_ID'):
        if kafka_connection_task and not kafka_connection_task.done():
            kafka_connection_task.cancel()
        kafka_connection_task = asyncio.create_task(connect_kafka_producer_with_event_nhs(), name="NHSKafkaProducerConnector")
    else:
        logger.warning("NHS Service: KAFKA_BOOTSTRAP_SERVERS or KAFKA_CLIENT_ID not set, Kafka producer will not start.")

    # Запуск Kafka Consumer
    logger.info("NHS Service: Starting Kafka consumers...")
    if not all(hasattr(settings, attr) for attr in ['KAFKA_BOOTSTRAP_SERVERS', 'KAFKA_CLIENT_ID', 'IDENTITY_VERIFICATION_REQUEST_TOPIC', 'KAFKA_NHS_VERIFICATION_GROUP_ID']):
        logger.error("NHS Service: Kafka settings for consumer are missing. Cannot start consumer.")
    else:
        consumer_config = {
            "topic": settings.IDENTITY_VERIFICATION_REQUEST_TOPIC,
            "group_id": settings.KAFKA_NHS_VERIFICATION_GROUP_ID,
            "handler": handle_identity_verification_request, # Убедитесь, что этот обработчик существует и корректен
            "name": "IdentityVerificationConsumerNHS"
        }
        task = asyncio.create_task(
            start_kafka_consumer(
                topic=consumer_config["topic"],
                group_id=consumer_config["group_id"],
                broker_url=settings.KAFKA_BOOTSTRAP_SERVERS,
                client_id_prefix=settings.KAFKA_CLIENT_ID,
                handler=consumer_config["handler"]
            ),
            name=consumer_config["name"]
        )
        consumer_tasks.append(task)
        logger.info(f"NHS Service: Consumer task '{consumer_config['name']}' for topic '{consumer_config['topic']}' created.")

    logger.info(f"[{settings.PROJECT_NAME}] Kafka consumers setup initiated. Tasks: {len(consumer_tasks)}")

    yield # Application is running

    logger.info(f"[{settings.PROJECT_NAME}] Shutting down via lifespan...")

    # Stop all consumer tasks
    # The `stop_kafka_consumer` from the refactored HMRC client stops one global consumer.
    # This will NOT work correctly if NHS service truly runs two independent consumers
    # managed by that same client code.
    # For now, calling it once, assuming it's a placeholder or the NHS client is different.
    # A proper solution needs the client to support multiple consumer instances.

    logger.info(f"[{settings.PROJECT_NAME}] Stopping Kafka consumers... ({len(consumer_tasks)} tasks identified)")
    for task in consumer_tasks:
        if not task.done():
            logger.info(f"[{settings.PROJECT_NAME}] Cancelling consumer task: {task.get_name()}")
            task.cancel()
            try:
                await task
                logger.info(f"[{settings.PROJECT_NAME}] Consumer task {task.get_name()} finished after cancellation.")
            except asyncio.CancelledError:
                logger.info(f"[{settings.PROJECT_NAME}] Consumer task {task.get_name()} was cancelled successfully.")
            except Exception as e:
                logger.error(f"[{settings.PROJECT_NAME}] Exception during consumer task {task.get_name()} shutdown: {e}", exc_info=True)
        else:
            logger.info(f"[{settings.PROJECT_NAME}] Consumer task {task.get_name()} already done.")

    # After tasks are cancelled, call the client's disconnect_kafka_consumers.
    # This is problematic if the client manages a single global instance and we had two tasks.
    # This assumes disconnect_kafka_consumers is a general cleanup.
    await disconnect_kafka_consumers()
    logger.info(f"[{settings.PROJECT_NAME}] Kafka client's disconnect_kafka_consumers called.")

    if kafka_connection_task and not kafka_connection_task.done():
        kafka_connection_task.cancel()
        try: await kafka_connection_task
        except asyncio.CancelledError: pass
        except Exception as e: logger.error(f"NHS: Error cancelling producer task: {e}")

    await disconnect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Lifespan shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="NHS Simulation Service for Microservice Prototype",
    version="0.1.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
if settings.BACKEND_CORS_ORIGINS:
    allow_origins = []
    if isinstance(settings.BACKEND_CORS_ORIGINS, str):
        allow_origins = ["*"] if settings.BACKEND_CORS_ORIGINS == "*" else [s.strip() for s in settings.BACKEND_CORS_ORIGINS.split(",")]
    elif isinstance(settings.BACKEND_CORS_ORIGINS, list):
        allow_origins = settings.BACKEND_CORS_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- Заглушки для API Маршрутов ---
# (В реальном приложении здесь будет полноценная логика, возможно с зависимостями)
# Pydantic модели для заглушек
class Patient(BaseModel):
    """Модель пациента для API."""
    id: str
    patientId: str
    name: str
    nhsNumber: str
    medicalHistory: str | None = None

class PatientCreate(BaseModel):
    """Модель для создания пациента."""
    name: str
    nhsNumber: str
    medicalHistory: str | None = None

api_router = APIRouter()

# Мок-данные
mock_nhsData: List[Dict[str, Any]] = [
    { "id": "1", "patientId": "P12345", "name": "Иван Петров", "nhsNumber": "NHS123456", "medicalHistory": "Общее хорошее здоровье" },
    { "id": "2", "patientId": "P67890", "name": "Мария Сидорова", "nhsNumber": "NHS789012", "medicalHistory": "Аллергия на пенициллин" }
]

@api_router.get("/patients", response_model=List[Patient])
async def get_patients():
    """Получает список всех пациентов."""
    logger.info(f"[{settings.PROJECT_NAME}] GET /patients requested")
    await asyncio.sleep(0.5)
    return mock_nhsData

@api_router.post("/patients", response_model=Patient, status_code=status.HTTP_201_CREATED)
async def create_patient(patient_in: PatientCreate):
    """Создает нового пациента."""
    logger.info(f"[{settings.PROJECT_NAME}] POST /patients requested for {patient_in.name}")
    new_patient_id = f"P{int(datetime.now().timestamp() % 100000)}"
    # Используем PatientCreate для создания словаря, затем Patient для валидации и создания экземпляра
    new_patient_data = patient_in.model_dump()
    new_patient_data['id'] = str(len(mock_nhsData) + 1)
    new_patient_data['patientId'] = new_patient_id

    validated_patient = Patient(**new_patient_data)
    mock_nhsData.append(validated_patient.model_dump()) # Сохраняем как dict для совместимости с mock_nhsData

    await asyncio.sleep(0.8)
    logger.info(f"[{settings.PROJECT_NAME}] Patient {new_patient_id} created.")
    return validated_patient

app.include_router(api_router, prefix=settings.API_V1_STR + "/nhs", tags=["nhs-patients"])

# --- Роутер для Записей к Врачу ---
appointment_router = APIRouter()

# Временное хранилище записей (вместо БД)
mock_appointments: Dict[str, AppointmentData] = {}

@appointment_router.post(
    "/appointments",
    response_model=AppointmentData,
    status_code=status.HTTP_202_ACCEPTED
)
async def request_appointment(
        appointment_request: AppointmentRequest,
        background_tasks: BackgroundTasks,
        request: Request,
        token_payload: TokenPayload = Depends(get_current_user_token_payload)
):
    """Запрашивает запись к врачу и отправляет событие в Kafka."""
    user_id = token_payload.id

    # Извлечение или генерация correlation_id
    correlation_id = request.headers.get("x-correlation-id")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
        logger.warning(f"X-Correlation-ID not found in request to /appointments, generated new: {correlation_id}")

    logger.info(f"Received appointment request from user {user_id} with correlation_id {correlation_id}: {appointment_request}")

    appointment_id_val = str(uuid.uuid4()) # Переименовал appointment_id в appointment_id_val чтобы не конфликтовать с полем в схеме
    requested_dt_utc = appointment_request.requested_datetime.astimezone(timezone.utc)

    # Сохраняем первичные данные (можно будет перенести в БД)
    appointment_data = AppointmentData(
        appointment_id=appointment_id_val,
        user_id=user_id,
        patient_identifier=appointment_request.patient_identifier,
        requested_datetime=requested_dt_utc,
        doctor_specialty=appointment_request.doctor_specialty,
        reason=appointment_request.reason,
        status=AppointmentStatus.REQUESTED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    mock_appointments[appointment_id_val] = appointment_data

    # Создаем сообщение для Kafka
    kafka_message = KafkaAppointmentRequest(
        appointment_id=appointment_id_val,
        user_id=user_id,
        patient_identifier=appointment_request.patient_identifier,
        requested_datetime=requested_dt_utc.isoformat(), # Убедимся что datetime сериализуется в строку для Kafka
        doctor_specialty=appointment_request.doctor_specialty,
        reason=appointment_request.reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id=correlation_id # Передаем correlation_id
    )

    # Отправляем сообщение в Kafka
    await send_kafka_message(
        topic=settings.KAFKA_TOPIC_MEDICAL_APPOINTMENT_REQUEST,
        message=kafka_message.model_dump()
    )
    logger.info(f"Appointment request {appointment_id_val} sent to Kafka topic {settings.KAFKA_TOPIC_MEDICAL_APPOINTMENT_REQUEST}, correlation_id: {correlation_id}")

    # Запускаем симуляцию обработки в фоне
    background_tasks.add_task(
        simulate_appointment_processing,
        appointment_id=appointment_id_val,
        user_id=user_id,
        request_data=kafka_message.model_dump(), # correlation_id будет здесь, так как он часть kafka_message
        correlation_id_param=correlation_id # Явно передаем для логирования в фоновой задаче, если нужно
    )
    logger.info(f"Background task scheduled for simulating processing of appointment {appointment_id_val}, correlation_id: {correlation_id}")

    # Возвращаем данные о созданной заявке
    return appointment_data

@appointment_router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentData
)
async def get_appointment_status(
        appointment_id: str,
        token_payload: TokenPayload = Depends(get_current_user_token_payload)
):
    """Получает статус записи к врачу по ее ID."""
    logger.debug(f"User {token_payload.id} requesting status for appointment {appointment_id}")
    appointment = mock_appointments.get(appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    # Простая проверка, что пользователь запрашивает свою запись (или админ)
    # В реальной системе нужна более сложная логика авторизации
    if appointment.user_id != token_payload.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this appointment")
    return appointment

# --- Подключение Роутеров ---
# Новый роутер для записей
app.include_router(appointment_router, prefix=settings.API_V1_STR + "/nhs", tags=["nhs-appointments"])

# Корневой эндпоинт
@app.get("/")
async def root():
    """Корневой эндпоинт, возвращает приветственное сообщение."""
    return {"message": f"Welcome to {settings.PROJECT_NAME}! Docs at /docs"}

@app.get(settings.API_V1_STR + "/nhs/healthcheck")
def healthcheck():
    """Эндпоинт для проверки работоспособности сервиса NHS."""
    logger.info(f"[{settings.PROJECT_NAME}] Healthcheck requested.")
    kafka_prod_status = "not_applicable" # Если продюсер не используется активно, или "ok"/"error"
    if hasattr(settings, 'KAFKA_BOOTSTRAP_SERVERS') and hasattr(settings, 'KAFKA_CLIENT_ID'): # Если продюсер настроен
        kafka_prod_status = "ok" if kafka_producer_ready.is_set() else "error"

    # Проверка состояния консьюмеров (упрощенная)
    consumer_status = "ok" if consumer_tasks and all(not task.done() or task.cancelled() for task in consumer_tasks) else "error_or_stopped"
    if not consumer_tasks and hasattr(settings, 'IDENTITY_VERIFICATION_REQUEST_TOPIC'): # Если должен быть консьюмер, но его нет
        consumer_status = "not_started"

    return {
        "status": "ok" if kafka_prod_status != "error" and consumer_status == "ok" else "degraded",
        "details": {
            "kafka_producer": kafka_prod_status,
            "kafka_consumer": consumer_status
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
import logging
import logging.config
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any, Dict, Optional

from .core.config import settings
from .kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    create_consumer_task,
    disconnect_kafka_consumers,
    send_kafka_message
)
from .kafka.handlers import (
    handle_verification_result,
    handle_appointment_result,
    simulate_appointment_processing
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
        "aiokafka": {"handlers": ["console"], "level": "WARNING"},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Управляет жизненным циклом Kafka producer и consumer tasks."""
    logger.info(f"[{settings.PROJECT_NAME}] Starting up via lifespan...")
    await connect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Lifespan: Creating Kafka consumer tasks...")

    # Создаем задачу для consumer'а верификации
    # Убедитесь, что KAFKA_TOPIC_IDENTITY_VERIFICATION_RESULT и KAFKA_CONSUMER_GROUP_ID_VERIFICATION определены в settings
    if hasattr(settings, 'KAFKA_TOPIC_IDENTITY_VERIFICATION_RESULT') and \
            hasattr(settings, 'KAFKA_CONSUMER_GROUP_ID_VERIFICATION'):
        create_consumer_task(
            topic=settings.KAFKA_TOPIC_IDENTITY_VERIFICATION_RESULT,
            group_id=settings.KAFKA_CONSUMER_GROUP_ID_VERIFICATION,
            handler=handle_verification_result
        )
    else:
        logger.warning("Settings for KAFKA_TOPIC_IDENTITY_VERIFICATION_RESULT or group_id not found, consumer task not started.")

    # Создаем задачу для consumer'а результатов записи к врачу
    # Убедитесь, что KAFKA_TOPIC_MEDICAL_APPOINTMENT_RESULT и KAFKA_CONSUMER_GROUP_ID_APPOINTMENT определены в settings
    if hasattr(settings, 'KAFKA_TOPIC_MEDICAL_APPOINTMENT_RESULT') and \
            hasattr(settings, 'KAFKA_CONSUMER_GROUP_ID_APPOINTMENT'):
        create_consumer_task(
            topic=settings.KAFKA_TOPIC_MEDICAL_APPOINTMENT_RESULT,
            group_id=settings.KAFKA_CONSUMER_GROUP_ID_APPOINTMENT,
            handler=handle_appointment_result
        )
    else:
        logger.warning("Settings for KAFKA_TOPIC_MEDICAL_APPOINTMENT_RESULT or group_id not found, consumer task not started.")

    logger.info(f"[{settings.PROJECT_NAME}] Kafka consumers setup initiated via lifespan.")
    yield
    logger.info(f"[{settings.PROJECT_NAME}] Shutting down via lifespan...")
    await disconnect_kafka_consumers()
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
        token_payload: TokenPayload = Depends(get_current_user_token_payload)
):
    """Запрашивает запись к врачу и отправляет событие в Kafka."""
    user_id = token_payload.id
    logger.info(f"Received appointment request from user {user_id}: {appointment_request}")

    appointment_id = str(uuid.uuid4())
    requested_dt_utc = appointment_request.requested_datetime.astimezone(timezone.utc)

    # Сохраняем первичные данные (можно будет перенести в БД)
    appointment_data = AppointmentData(
        appointment_id=appointment_id,
        user_id=user_id,
        patient_identifier=appointment_request.patient_identifier,
        requested_datetime=requested_dt_utc,
        doctor_specialty=appointment_request.doctor_specialty,
        reason=appointment_request.reason,
        status=AppointmentStatus.REQUESTED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    mock_appointments[appointment_id] = appointment_data

    # Создаем сообщение для Kafka
    kafka_message = KafkaAppointmentRequest(
        appointment_id=appointment_id,
        user_id=user_id,
        patient_identifier=appointment_request.patient_identifier,
        requested_datetime=requested_dt_utc,
        doctor_specialty=appointment_request.doctor_specialty,
        reason=appointment_request.reason
    )

    # Отправляем сообщение в Kafka
    await send_kafka_message(
        topic=settings.KAFKA_TOPIC_MEDICAL_APPOINTMENT_REQUEST,
        message=kafka_message.model_dump(mode='json')
    )
    logger.info(f"Appointment request {appointment_id} sent to Kafka topic {settings.KAFKA_TOPIC_MEDICAL_APPOINTMENT_REQUEST}")

    # Запускаем симуляцию обработки в фоне
    background_tasks.add_task(
        simulate_appointment_processing,
        appointment_id=appointment_id,
        user_id=user_id,
        request_data=kafka_message.model_dump(mode='json')
    )
    logger.info(f"Background task scheduled for simulating processing of appointment {appointment_id}")

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
    return {"status": "ok", "service": settings.PROJECT_NAME, "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
import logging
import logging.config
import asyncio
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any, Dict, Optional

from app.core.config import settings
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    create_consumer_task,
    disconnect_kafka_consumers,
    send_kafka_message
)
from app.kafka.handlers import (
    handle_verification_result,
    handle_appointment_result,
    simulate_appointment_processing
)
# Заглушка для зависимости проверки токена (пока не реализуем)
# from app.dependencies import get_current_verified_user
# Импортируем зависимость и схемы
from app.dependencies import get_current_user_token_payload, TokenPayload
from app.schemas.appointment import (
    AppointmentRequest,
    AppointmentData,
    AppointmentStatus,
    KafkaAppointmentRequest,
    KafkaAppointmentResult
)

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

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="NHS Simulation Service for Microservice Prototype",
    version="0.1.0",
    lifespan= lambda _app: asyncio.asynccontextmanager(startup_event, shutdown_event)()
)

# --- Обработчики событий Startup/Shutdown ---
async def startup_event():
    logger.info(f"[{settings.PROJECT_NAME}] Starting up...")
    # Подключение Kafka
    await connect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Startup: Creating Kafka consumer tasks...")
    # Создаем задачу для consumer'а верификации
    create_consumer_task(
        topic=settings.KAFKA_TOPIC_IDENTITY_VERIFICATION_RESULT,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID_VERIFICATION,
        handler=handle_verification_result
    )
    # Создаем задачу для consumer'а результатов записи к врачу
    create_consumer_task(
        topic=settings.KAFKA_TOPIC_MEDICAL_APPOINTMENT_RESULT,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID_APPOINTMENT,
        handler=handle_appointment_result
    )
    logger.info(f"[{settings.PROJECT_NAME}] Startup complete.")

async def shutdown_event():
    logger.info(f"[{settings.PROJECT_NAME}] Shutting down...")
    await disconnect_kafka_consumers()
    await disconnect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Shutdown complete.")

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
    id: str
    patientId: str
    name: str
    nhsNumber: str
    medicalHistory: str | None = None

class PatientCreate(BaseModel):
    name: str
    nhsNumber: str
    medicalHistory: str | None = None

api_router = APIRouter()

# Мок-данные
mock_nhsData = [
    { "id": "1", "patientId": "P12345", "name": "Иван Петров", "nhsNumber": "NHS123456", "medicalHistory": "Общее хорошее здоровье" },
    { "id": "2", "patientId": "P67890", "name": "Мария Сидорова", "nhsNumber": "NHS789012", "medicalHistory": "Аллергия на пенициллин" }
]

@api_router.get("/patients", response_model=List[Patient])
async def get_patients(# current_user: Any = Depends(get_current_verified_user) # Защита
):
    logger.info(f"[{settings.PROJECT_NAME}] GET /patients requested")
    # Имитация задержки
    await asyncio.sleep(0.5)
    return mock_nhsData

@api_router.post("/patients", response_model=Patient, status_code=status.HTTP_201_CREATED)
async def create_patient(patient_in: PatientCreate, # current_user: Any = Depends(get_current_verified_user)
                         ):
    logger.info(f"[{settings.PROJECT_NAME}] POST /patients requested for {patient_in.name}")
    new_patient_id = f"P{int(datetime.now().timestamp() % 100000)}"
    new_patient = Patient(
        id=str(len(mock_nhsData) + 1),
        patientId=new_patient_id,
        **patient_in.model_dump()
    )
    mock_nhsData.append(new_patient.model_dump()) # Добавляем как dict
    # Имитация задержки
    await asyncio.sleep(0.8)
    logger.info(f"[{settings.PROJECT_NAME}] Patient {new_patient_id} created.")
    # TODO: Отправка medical.appointment.request в Kafka
    return new_patient

app.include_router(api_router, prefix=settings.API_V1_STR + "/nns", tags=["nns"])

# --- Роутер для Записей к Врачу ---
appointment_router = APIRouter()

# Временное хранилище записей (вместо БД)
mock_appointments: Dict[str, AppointmentData] = {}

@appointment_router.post(
    "/",
    response_model=AppointmentData,
    status_code=status.HTTP_202_ACCEPTED # 202 Accepted, т.к. обработка асинхронная
)
async def request_appointment(
        appointment_request: AppointmentRequest,
        background_tasks: BackgroundTasks,
        token_payload: TokenPayload = Depends(get_current_user_token_payload)
):
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
    "/{appointment_id}",
    response_model=AppointmentData
)
async def get_appointment_status(
        appointment_id: str,
        token_payload: TokenPayload = Depends(get_current_user_token_payload)
):
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
app.include_router(appointment_router, prefix=settings.API_V1_STR + "/nns", tags=["appointments"])

# Корневой эндпоинт
@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}! Docs at /docs"}
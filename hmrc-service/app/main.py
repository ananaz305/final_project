import logging
import logging.config
import asyncio
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any
from datetime import datetime

from app.core.config import settings
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    create_consumer_task,
    disconnect_kafka_consumer
)
from app.kafka.handlers import handle_nin_verification_request, schedule_death_notification_simulation
# Заглушка для зависимости проверки токена
# from app.dependencies import get_current_verified_user

# Настройка логирования
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
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# --- Обработчики событий Startup/Shutdown ---
death_simulation_task: asyncio.Task | None = None

@app.on_event("startup")
async def startup_event():
    global death_simulation_task
    logger.info(f"[{settings.PROJECT_NAME}] Starting up...")
    # Подключение Kafka
    await connect_kafka_producer()
    # Запуск Kafka Consumer'а для запросов на верификацию
    create_consumer_task(
        settings.IDENTITY_VERIFICATION_REQUEST_TOPIC,
        settings.KAFKA_VERIFICATION_GROUP_ID,
        handle_nin_verification_request
    )
    # Запуск имитации события смерти
    death_simulation_task = asyncio.create_task(schedule_death_notification_simulation())
    logger.info(f"[{settings.PROJECT_NAME}] Startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    global death_simulation_task
    logger.info(f"[{settings.PROJECT_NAME}] Shutting down...")
    # Отменяем задачу имитации, если она есть
    if death_simulation_task and not death_simulation_task.done():
        death_simulation_task.cancel()
        try:
            await death_simulation_task
        except asyncio.CancelledError:
            logger.info(f"[{settings.PROJECT_NAME}] Death simulation task cancelled.")

    await disconnect_kafka_consumer()
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
class TaxRecord(BaseModel):
    id: str
    taxId: str
    name: str
    taxNumber: str
    taxYear: str
    taxAmount: float

class TaxRecordCreate(BaseModel):
    name: str
    taxNumber: str
    taxYear: str
    taxAmount: float

api_router = APIRouter()

# Мок-данные
mock_taxRecords = [
    { "id": "1", "taxId": "T12345", "name": "Иван Петров", "taxNumber": "UTR123456", "taxYear": "2022-2023", "taxAmount": 5500.0 },
    { "id": "2", "taxId": "T67890", "name": "Мария Сидорова", "taxNumber": "UTR789012", "taxYear": "2022-2023", "taxAmount": 7200.0 }
]

@api_router.get("/tax-records", response_model=List[TaxRecord])
async def get_tax_records(# current_user: Any = Depends(get_current_verified_user)
):
    logger.info(f"[{settings.PROJECT_NAME}] GET /tax-records requested")
    await asyncio.sleep(0.4)
    return mock_taxRecords

@api_router.post("/tax-records", response_model=TaxRecord, status_code=status.HTTP_201_CREATED)
async def create_tax_record(record_in: TaxRecordCreate, # current_user: Any = Depends(get_current_verified_user)
                            ):
    logger.info(f"[{settings.PROJECT_NAME}] POST /tax-records requested for {record_in.name}")
    new_tax_id = f"T{int(datetime.now().timestamp() % 100000)}"
    new_record = TaxRecord(
        id=str(len(mock_taxRecords) + 1),
        taxId=new_tax_id,
        **record_in.model_dump()
    )
    mock_taxRecords.append(new_record.model_dump())
    await asyncio.sleep(0.6)
    logger.info(f"[{settings.PROJECT_NAME}] Tax record {new_tax_id} created.")
    return new_record

app.include_router(api_router, prefix=settings.API_V1_STR + "/hmrc", tags=["hmrc"])

# Корневой эндпоинт
@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}! Docs at /docs"}
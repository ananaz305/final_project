import logging
import logging.config
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any
from datetime import datetime

from app.core.config import settings
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    start_kafka_consumer,
    stop_kafka_consumer
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

# --- Lifespan for startup/shutdown ---
death_simulation_task: asyncio.Task | None = None
kafka_consumer_topics = [settings.IDENTITY_VERIFICATION_REQUEST_TOPIC]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global death_simulation_task
    logger.info(f"[{settings.PROJECT_NAME}] Starting up via lifespan...")

    # Подключение Kafka Producer
    await connect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Kafka producer connected.")

    # Запуск Kafka Consumer'а для запросов на верификацию
    # start_kafka_consumer теперь сама создает задачу и управляет ей
    await start_kafka_consumer(
        topic=kafka_consumer_topics,
        group_id=settings.KAFKA_VERIFICATION_GROUP_ID,
        handler=handle_nin_verification_request
    )
    logger.info(f"[{settings.PROJECT_NAME}] Kafka consumer for {kafka_consumer_topics} started.")

    # Запуск имитации события смерти
    if settings.SIMULATE_DEATH_NOTIFICATIONS: # Предполагаем, что есть такая настройка
        death_simulation_task = asyncio.create_task(schedule_death_notification_simulation())
        logger.info(f"[{settings.PROJECT_NAME}] Death notification simulation task scheduled.")
    else:
        logger.info(f"[{settings.PROJECT_NAME}] Death notification simulation is disabled by config.")

    yield # Приложение работает

    logger.info(f"[{settings.PROJECT_NAME}] Shutting down via lifespan...")

    # Отменяем задачу имитации, если она есть и запущена
    if death_simulation_task and not death_simulation_task.done():
        logger.info(f"[{settings.PROJECT_NAME}] Cancelling death simulation task...")
        death_simulation_task.cancel()
        try:
            await death_simulation_task
            logger.info(f"[{settings.PROJECT_NAME}] Death simulation task finished after cancellation.")
        except asyncio.CancelledError:
            logger.info(f"[{settings.PROJECT_NAME}] Death simulation task was cancelled successfully.")
        except Exception as e:
            logger.error(f"[{settings.PROJECT_NAME}] Exception during death simulation task shutdown: {e}", exc_info=True)

    # Остановка Kafka Consumer
    # stop_kafka_consumer теперь корректно обрабатывает остановку задачи consumer'а
    await stop_kafka_consumer()
    logger.info(f"[{settings.PROJECT_NAME}] Kafka consumer stopped.")

    # Отключение Kafka Producer
    await disconnect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Kafka producer disconnected.")

    logger.info(f"[{settings.PROJECT_NAME}] Lifespan shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
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
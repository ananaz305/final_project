import logging
import logging.config
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any, Optional
from datetime import datetime

from app.core.config import settings
from shared.kafka_client_lib.client import (
    connect_kafka_producer, # HMRC may not produce messages
    disconnect_kafka_producer,
    start_kafka_consumer,
    disconnect_kafka_consumers
)
from shared.kafka_client_lib.exceptions import KafkaConnectionError
from app.kafka.handlers import handle_nin_verification_request, handle_death_notification

# Logging settings
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "app": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "shared": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "aiokafka": {"handlers": ["console"], "level": "WARNING"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app.hmrc-service")

consumer_tasks: List[asyncio.Task] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_tasks
    logger.info("HMRC Service: Starting up...")

    # Starting Kafka Producer
    try:
        await connect_kafka_producer(
            broker_url=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=settings.KAFKA_CLIENT_ID
        )
        logger.info("HMRC Service: Kafka producer connected successfully.")
    except KafkaConnectionError as e:
        logger.error(f"HMRC Service: Failed to connect Kafka producer: {e}")
    except AttributeError:
        logger.error("HMRC Service: Kafka settings for producer are missing (KAFKA_BOOTSTRAP_SERVERS or KAFKA_CLIENT_ID). Producer not started.")

    # Starting Kafka Consumer
    logger.info("HMRC Service: Starting Kafka consumers...")
    if not all(hasattr(settings, attr) for attr in ['KAFKA_BOOTSTRAP_SERVERS', 'KAFKA_CLIENT_ID', 'HMRC_DEATH_NOTIFICATION_TOPIC', 'KAFKA_HMRC_DEATH_EVENT_GROUP_ID']):
        logger.error("HMRC Service: Kafka settings for consumer are missing. Cannot start consumer.")
    else:
        consumer_config = {
            "topic": settings.HMRC_DEATH_NOTIFICATION_TOPIC,
            "group_id": settings.KAFKA_HMRC_DEATH_EVENT_GROUP_ID,
            "handler": handle_death_notification,
            "name": "DeathNotificationConsumerHMRC"
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
        task = asyncio.create_task(
            start_kafka_consumer(
                topic="identity.verification.request",
                group_id="reg-login-verification-group",
                broker_url=settings.KAFKA_BOOTSTRAP_SERVERS,
                client_id_prefix=settings.KAFKA_CLIENT_ID,
                handler=handle_nin_verification_request
            ),
            name="IdentityVerificationConsumerHMRC"
        )
        logger.info(f"HMRC Service: Consumer task '{consumer_config['name']}' for topic '{consumer_config['topic']}' created.")

    yield

    logger.info("HMRC Service: Shutting down...")
    for task in consumer_tasks:
        if not task.done(): task.cancel()
    if consumer_tasks: await asyncio.gather(*consumer_tasks, return_exceptions=True)
    consumer_tasks.clear()

    await disconnect_kafka_consumers()
    # If HMRC does not produce messages, disconnect_kafka_producer() is not needed
    await disconnect_kafka_producer()
    logger.info("HMRC Service: Lifespan shutdown complete.")

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

# --- Stubs for API Routes ---
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

# Mock data
mock_taxRecords = [
    { "id": "1", "taxId": "T12345", "name": "John Doe", "taxNumber": "UTR123456", "taxYear": "2022-2023", "taxAmount": 5500.0 },
    { "id": "2", "taxId": "T67890", "name": "John Jonson", "taxNumber": "UTR789012", "taxYear": "2022-2023", "taxAmount": 7200.0 }
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

# Root endpoint
@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}! Docs at /docs"}

# Healthcheck endpoint for HMRC service
@app.get(f"{settings.API_V1_STR}/healthcheck")
async def healthcheck():
    consumer_status = "ok" if consumer_tasks and all(not task.done() or task.cancelled() for task in consumer_tasks) else "error_or_stopped"
    if not consumer_tasks and hasattr(settings, 'HMRC_DEATH_NOTIFICATION_TOPIC'):
        consumer_status = "not_started"

    return {
        "status": "ok" if consumer_status == "ok" else "degraded",
        "details": {
            "kafka_consumer": consumer_status
        }
    }
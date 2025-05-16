import logging
import logging.config
import asyncio
from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import init_db, test_connection
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    start_kafka_consumer,
    stop_kafka_consumer,
)
from app.kafka.handlers import handle_verification_result, handle_death_notification
from app.api.v1 import auth # Импортируем роутер
from app.api import google_auth  # Добавляем импорт

# Настройка логирования
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
        "aiokafka": {"handlers": ["console"], "level": "WARNING"}, # Уменьшаем шум от aiokafka
        "sqlalchemy.engine": {"handlers": ["console"], "level": "WARNING"}, # Логи SQL
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app")

# Store consumer tasks to manage them
consumer_tasks: List[asyncio.Task] = []

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manages application startup and shutdown events."""
    global consumer_tasks
    logger.info("Starting up application via lifespan...")

    # Database initialization and connection test
    await test_connection()
    # await init_db() # Uncomment if automatic table creation is desired on startup

    # Connect Kafka Producer
    await connect_kafka_producer()
    logger.info("Kafka producer connected.")

    # Start Kafka Consumers
    logger.info("Starting Kafka consumers via lifespan...")

    # Consumer for identity verification results
    if hasattr(settings, 'IDENTITY_VERIFICATION_RESULT_TOPIC') and \
            hasattr(settings, 'KAFKA_VERIFICATION_GROUP_ID'):
        task1 = asyncio.create_task(
            start_kafka_consumer(
                topics=[settings.IDENTITY_VERIFICATION_RESULT_TOPIC],
                group_id=settings.KAFKA_VERIFICATION_GROUP_ID,
                message_handler=handle_verification_result
            ),
            name="VerificationResultConsumerRegLogin"
        )
        consumer_tasks.append(task1)
        logger.info(f"Consumer task for {settings.IDENTITY_VERIFICATION_RESULT_TOPIC} created.")
    else:
        logger.warning("Settings for IDENTITY_VERIFICATION_RESULT_TOPIC or KAFKA_VERIFICATION_GROUP_ID not found.")

    # Consumer for HMRC death notifications
    if hasattr(settings, 'HMRC_DEATH_NOTIFICATION_TOPIC') and \
            hasattr(settings, 'KAFKA_DEATH_EVENT_GROUP_ID'):
        task2 = asyncio.create_task(
            start_kafka_consumer(
                topics=[settings.HMRC_DEATH_NOTIFICATION_TOPIC],
                group_id=settings.KAFKA_DEATH_EVENT_GROUP_ID,
                message_handler=handle_death_notification
            ),
            name="DeathNotificationConsumerRegLogin"
        )
        consumer_tasks.append(task2)
        logger.info(f"Consumer task for {settings.HMRC_DEATH_NOTIFICATION_TOPIC} created.")
    else:
        logger.warning("Settings for HMRC_DEATH_NOTIFICATION_TOPIC or KAFKA_DEATH_EVENT_GROUP_ID not found.")

    logger.info(f"Kafka consumers setup initiated. Tasks: {len(consumer_tasks)}")

    yield # Application is running

    logger.info("Shutting down application via lifespan...")

    # Stop all consumer tasks
    logger.info(f"Stopping Kafka consumer tasks... ({len(consumer_tasks)} identified)")
    for task in consumer_tasks:
        if not task.done():
            logger.info(f"Cancelling consumer task: {task.get_name()}")
            task.cancel()
            try:
                await task
                logger.info(f"Consumer task {task.get_name()} finished after cancellation.")
            except asyncio.CancelledError:
                logger.info(f"Consumer task {task.get_name()} was cancelled successfully.")
            except Exception as e:
                logger.error(f"Exception during consumer task {task.get_name()} shutdown: {e}", exc_info=True)
        else:
            logger.info(f"Consumer task {task.get_name()} already done.")

    # Call the client's stop_kafka_consumer (again, problematic if client uses one global)
    await stop_kafka_consumer()
    logger.info("Kafka client's stop_kafka_consumer called.")

    await disconnect_kafka_producer()
    logger.info("Kafka producer disconnected.")

    # Database engine will be closed automatically by sqlalchemy or managed by lifespan if needed
    logger.info("Lifespan shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan # Use lifespan
)

# --- CORS Middleware ---
if settings.BACKEND_CORS_ORIGINS:
    # Разрешаем все источники, если строка или список не пустые
    allow_origins = []
    if isinstance(settings.BACKEND_CORS_ORIGINS, str):
        if settings.BACKEND_CORS_ORIGINS == "*":
            allow_origins = ["*"]
        else:
            allow_origins = [s.strip() for s in settings.BACKEND_CORS_ORIGINS.split(",")]
    elif isinstance(settings.BACKEND_CORS_ORIGINS, list):
        allow_origins = settings.BACKEND_CORS_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Подключение Роутеров ---
    app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["auth"])
    app.include_router(google_auth.router, prefix=f"{settings.API_V1_STR}/auth/google", tags=["google-auth"])

    # --- Корневой эндпоинт ---
    @app.get("/")
    async def root():
        return {"message": f"Welcome to {settings.PROJECT_NAME}! Docs at /docs"}

    # Точка входа для Uvicorn (если запускать как python -m app.main)
    # if __name__ == "__main__":
    #     import uvicorn
    #     uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) # Порт по умолчанию 8000
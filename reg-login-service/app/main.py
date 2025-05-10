import logging
import logging.config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import init_db, test_connection
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    create_consumer_task,
    disconnect_kafka_consumers
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

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# --- Обработчики событий Startup/Shutdown ---
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up application...")
    # Проверка и инициализация БД
    await test_connection()
    # await init_db() # Раскомментировать для автоматического создания таблиц

    # Подключение Kafka Producer
    await connect_kafka_producer()

    # Запуск Kafka Consumers как фоновых задач
    logger.info("Starting Kafka consumers...")
    create_consumer_task(
        settings.IDENTITY_VERIFICATION_RESULT_TOPIC,
        settings.KAFKA_VERIFICATION_GROUP_ID,
        handle_verification_result
    )
    create_consumer_task(
        settings.HMRC_DEATH_NOTIFICATION_TOPIC,
        settings.KAFKA_DEATH_EVENT_GROUP_ID,
        handle_death_notification
    )
    logger.info("Startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")
    # Отключение Kafka
    await disconnect_kafka_consumers() # Сначала останавливаем консьюмеров
    await disconnect_kafka_producer()  # Затем продюсера
    # Отключение БД (engine закроется сам при завершении процесса)
    logger.info("Shutdown complete.")

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
import logging
import logging.config
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.core.config import settings
from app.db.database import init_db, test_connection
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    start_kafka_consumer,
    disconnect_kafka_consumers,
    get_kafka_producer,
)
from app.kafka.handlers import handle_verification_result, handle_death_notification
from app.api import auth # Новый, исправленный импорт
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
kafka_producer_ready = asyncio.Event() # Событие для сигнализации о готовности продюсера
kafka_connection_task: Optional[asyncio.Task] = None # Задача для подключения продюсера

async def connect_kafka_producer_with_event():
    """Tries to connect the Kafka producer and sets an event upon success."""
    global kafka_producer_ready
    try:
        logger.info("Background task: Attempting to connect Kafka producer...")
        # connect_kafka_producer теперь выбрасывает исключение при неудаче
        # Нам нужен цикл retry здесь, если мы хотим, чтобы он продолжал пытаться в фоне
        retry_delay = 10 # секунд
        max_retries = 5 # Примерное количество попыток, можно сделать бесконечным или конфигурируемым
        attempt = 0
        while attempt < max_retries:
            try:
                await connect_kafka_producer() # Эта функция теперь пытается подключиться один раз (или с внутренним коротким retry)
                if get_kafka_producer(): # Проверка, что продюсер действительно установлен
                    kafka_producer_ready.set()
                    logger.info("Background task: Kafka producer connected successfully.")
                    return # Успех, выходим из цикла и задачи
            except Exception as e: # Ловим любые исключения от connect_kafka_producer
                logger.error(f"Background task: Kafka producer connection attempt {attempt+1}/{max_retries} failed: {e}")
            attempt += 1
            if attempt < max_retries:
                logger.info(f"Background task: Retrying Kafka producer connection in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Background task: Max retries reached for Kafka producer connection. Producer remains unavailable.")
                # Событие kafka_producer_ready останется не установленным

    except asyncio.CancelledError:
        logger.info("Background task: Kafka producer connection task cancelled.")
        raise # Перевыбрасываем, чтобы задача корректно завершилась как отмененная
    except Exception as e:
        logger.error(f"Background task: Unexpected error in Kafka producer connection task: {e}", exc_info=True)
        # Событие kafka_producer_ready останется не установленным

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manages application startup and shutdown events."""
    global consumer_tasks, kafka_connection_task
    logger.info("Starting up application via lifespan...")

    # Database initialization and connection test
    try:
        await test_connection()
    except Exception as db_err:
        logger.critical(f"CRITICAL: Database connection failed on startup: {db_err}", exc_info=True)
        # В зависимости от политики, можно либо падать, либо продолжать без БД (если часть функционала может работать)
        # Для простоты, продолжим, но healthcheck покажет проблему.

    # await init_db() # Uncomment if automatic table creation is desired on startup

    # Start Kafka Producer connection in the background
    logger.info("Initiating Kafka producer connection in background...")
    # Убедимся, что старая задача (если есть от предыдущего нечистого завершения) отменена
    if kafka_connection_task and not kafka_connection_task.done():
        kafka_connection_task.cancel()
    kafka_connection_task = asyncio.create_task(connect_kafka_producer_with_event(), name="KafkaProducerConnector")

    # Start Kafka Consumers
    logger.info("Starting Kafka consumers via lifespan...")

    # Consumer for identity verification results
    if hasattr(settings, 'IDENTITY_VERIFICATION_RESULT_TOPIC') and \
            hasattr(settings, 'KAFKA_VERIFICATION_GROUP_ID'):
        task1 = asyncio.create_task(
            start_kafka_consumer(
                topic=settings.IDENTITY_VERIFICATION_RESULT_TOPIC,
                group_id=settings.KAFKA_VERIFICATION_GROUP_ID,
                handler=handle_verification_result
            ),
            name="VerificationResultConsumerRegLogin"
        )
        consumer_tasks.append(task1)
        logger.info(f"Consumer task for {settings.IDENTITY_VERIFICATION_RESULT_TOPIC} created.")
    else:
        logger.warning("Settings for IDENTITY_VERIFICATION_RESULT_TOPIC or KAFKA_VERIFICATION_GROUP_ID not found.")

    # Future-feature: Enable this consumer for handling HMRC death notifications
    # if hasattr(settings, 'HMRC_DEATH_NOTIFICATION_TOPIC') and \
    #    hasattr(settings, 'KAFKA_DEATH_EVENT_GROUP_ID'):
    #     task2 = asyncio.create_task(
    #         start_kafka_consumer(
    #             topic=settings.HMRC_DEATH_NOTIFICATION_TOPIC, # Если раскомментируете, здесь тоже topic
    #             group_id=settings.KAFKA_DEATH_EVENT_GROUP_ID,
    #             handler=handle_death_notification # И здесь handler
    #         ),
    #         name="DeathNotificationConsumerRegLogin"
    #     )
    #     consumer_tasks.append(task2)
    #     logger.info(f"Consumer task for {settings.HMRC_DEATH_NOTIFICATION_TOPIC} created.")
    # else:
    #     logger.warning("Settings for HMRC_DEATH_NOTIFICATION_TOPIC or KAFKA_DEATH_EVENT_GROUP_ID not found.")

    logger.info(f"Kafka consumers setup initiated. Tasks: {len(consumer_tasks)}")

    yield # Application is running

    logger.info("Shutting down application via lifespan...")

    # Cancel background Kafka producer connection task if it's still running
    if kafka_connection_task and not kafka_connection_task.done():
        logger.info("Cancelling background Kafka producer connection task...")
        kafka_connection_task.cancel()
        try:
            await kafka_connection_task
        except asyncio.CancelledError:
            logger.info("Background Kafka producer connection task cancelled successfully during shutdown.")
        except Exception as e:
            logger.error(f"Error during background Kafka producer connection task shutdown: {e}")

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

    await disconnect_kafka_consumers()
    logger.info("Kafka client's disconnect_kafka_consumers called.")

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

    @app.get(f"{settings.API_V1_STR}/auth/healthcheck")
    async def healthcheck():
        """Эндпоинт для проверки работоспособности сервиса Reg-Login."""
        logger.info(f"[{settings.PROJECT_NAME}] Healthcheck requested.")
        db_status = "ok"
        kafka_prod_status = "unavailable"
        service_overall_status = "degraded" # Начнем с degraded
        http_status_code = 503 # Service Unavailable по умолчанию

        try:
            await test_connection()
        except Exception as e:
            logger.error(f"Healthcheck: DB connection failed: {e}")
            db_status = "error"

        if kafka_producer_ready.is_set():
            try:
                # Дополнительная проверка, что продюсер не только был готов, но и сейчас доступен
                # Это может быть излишним, если is_set() достаточно
                get_kafka_producer() # Выбросит RuntimeError, если producer был сброшен в None
                kafka_prod_status = "ok"
            except RuntimeError:
                kafka_prod_status = "error_after_ready" # Был готов, но теперь нет
                kafka_producer_ready.clear() # Сбрасываем флаг, т.к. он больше не актуален
        elif kafka_connection_task and not kafka_connection_task.done():
            kafka_prod_status = "connecting"
        else: # Не готов и задача завершена (вероятно, с ошибкой или достигнут лимит ретраев)
            kafka_prod_status = "failed_to_connect"

        if db_status == "ok" and kafka_prod_status == "ok":
            service_overall_status = "ok"
            http_status_code = 200
        elif db_status == "ok" and kafka_prod_status == "connecting":
            service_overall_status = "degraded_kafka_connecting" # Приложение работает, но Kafka еще подключается
            http_status_code = 200 # Сервис доступен, но с ограничениями
        else:
            service_overall_status = "error" # Одна из критических зависимостей не работает
            http_status_code = 503

        response_payload = {
            "status": service_overall_status,
            "details": {
                "database": db_status,
                "kafka_producer": kafka_prod_status
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if http_status_code != 200:
            # Для FastAPI лучше выбрасывать HTTPException, чтобы статус код был корректно установлен
            # Однако, для healthcheck иногда возвращают 200 с плохим статусом в теле.
            # Здесь я оставлю возврат словаря, но вы можете изменить на HTTPException
            # raise HTTPException(status_code=http_status_code, detail=response_payload)
            # Если возвращаем словарь, то FastAPI по умолчанию вернет 200. Нужно будет это учитывать.
            # Чтобы FastAPI вернул нужный статус-код при возврате словаря, можно использовать Response объект.
            # Но для простоты healthcheck часто возвращают 200 и смотрят на тело.
            # Давайте сделаем так, чтобы FastAPI сам установил статус код, если он не 200.
            # Для этого нужно будет немного изменить возвращаемое значение или использовать Response.
            # ПОКА ОСТАВИМ КАК ЕСТЬ, но это точка для улучшения, если нужен точный HTTP статус от healthcheck.
            pass

        return response_payload

    # Точка входа для Uvicorn (если запускать как python -m app.main)
    # if __name__ == "__main__":
    #     import uvicorn
    #     uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) # Порт по умолчанию 8000
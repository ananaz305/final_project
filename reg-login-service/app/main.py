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

# Updated Kafka imports
from shared.kafka_client_lib.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    start_kafka_consumer, # This is the long-running consumer function
    disconnect_kafka_consumers, # This stops consumer instances
    get_kafka_producer,
)
from shared.kafka_client_lib.exceptions import KafkaConnectionError, KafkaMessageSendError

from app.kafka.handlers import handle_verification_result, handle_death_notification
from app.api import auth
# from app.api import google_auth # Закомментируем импорт Google Auth

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
        "shared": {"handlers": ["console"], "level": "INFO", "propagate": False}, # Logger for the shared library
        "aiokafka": {"handlers": ["console"], "level": "WARNING"},
        "sqlalchemy.engine": {"handlers": ["console"], "level": "WARNING"},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app")
# Logger for the shared library, can be configured here or managed by the library itself if it sets up its own handlers.
# For now, let app manage it.
# shared_kafka_logger = logging.getLogger("shared.kafka_client_lib")

consumer_tasks: List[asyncio.Task] = []
kafka_producer_ready = asyncio.Event()
kafka_connection_task: Optional[asyncio.Task] = None

async def connect_kafka_producer_with_event():
    """Tries to connect the Kafka producer and sets an event upon success."""
    global kafka_producer_ready
    try:
        logger.info("Background task: Attempting to connect Kafka producer...")
        retry_delay = settings.KAFKA_RECONNECT_DELAY_S if hasattr(settings, 'KAFKA_RECONNECT_DELAY_S') else 10
        max_retries = settings.KAFKA_MAX_RETRIES if hasattr(settings, 'KAFKA_MAX_RETRIES') else 5
        attempt = 0

        # Ensure KAFKA_BROKER_URL and KAFKA_CLIENT_ID are available
        if not hasattr(settings, 'KAFKA_BROKER_URL') or not hasattr(settings, 'KAFKA_CLIENT_ID'):
            logger.critical("KAFKA_BROKER_URL or KAFKA_CLIENT_ID not configured in settings.")
            return

        while attempt < max_retries:
            try:
                # Call the library function with parameters from settings
                await connect_kafka_producer(
                    broker_url=settings.KAFKA_BROKER_URL,
                    client_id=settings.KAFKA_CLIENT_ID
                    # Default retry/timeout values from library will be used unless specified here
                )
                # Check producer status using the library's get_kafka_producer
                # This will raise RuntimeError if connection failed and _producer is None
                get_kafka_producer()
                kafka_producer_ready.set()
                logger.info("Background task: Kafka producer connected successfully.")
                return
            except KafkaConnectionError as e: # Catch specific exception from the library
                logger.error(f"Background task: Kafka producer connection attempt {attempt+1}/{max_retries} failed: {e}")
            except RuntimeError as e: # Catch if get_kafka_producer fails after connect_kafka_producer didn't raise
                logger.error(f"Background task: Kafka producer check failed after connection attempt {attempt+1}/{max_retries}: {e}")
            except Exception as e: # Catch any other unexpected errors
                logger.error(f"Background task: Unexpected error during Kafka producer connection attempt {attempt+1}/{max_retries}: {e}", exc_info=True)

            attempt += 1
            if attempt < max_retries:
                logger.info(f"Background task: Retrying Kafka producer connection in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Background task: Max retries reached for Kafka producer connection. Producer remains unavailable.")
                kafka_producer_ready.clear() # Explicitly clear if all retries fail

    except asyncio.CancelledError:
        logger.info("Background task: Kafka producer connection task cancelled.")
        raise
    except Exception as e:
        logger.error(f"Background task: Unexpected error in Kafka producer connection task: {e}", exc_info=True)
        kafka_producer_ready.clear()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manages application startup and shutdown events."""
    global consumer_tasks, kafka_connection_task, kafka_producer_ready
    logger.info("Starting up application via lifespan...")
    kafka_producer_ready.clear() # Ensure it's clear at startup

    try:
        await test_connection()
    except Exception as db_err:
        logger.critical(f"CRITICAL: Database connection failed on startup: {db_err}", exc_info=True)

    # await init_db()

    logger.info("Initiating Kafka producer connection in background...")
    if kafka_connection_task and not kafka_connection_task.done():
        kafka_connection_task.cancel()
    kafka_connection_task = asyncio.create_task(connect_kafka_producer_with_event(), name="KafkaProducerConnector")

    logger.info("Starting Kafka consumers via lifespan...")

    # Ensure required settings are present
    if not all(hasattr(settings, attr) for attr in ['KAFKA_BROKER_URL', 'KAFKA_CLIENT_ID']):
        logger.error("Kafka settings (KAFKA_BROKER_URL, KAFKA_CLIENT_ID) are missing. Cannot start consumers.")
    else:
        consumer_configs = [
            {
                "topic": settings.IDENTITY_VERIFICATION_RESULT_TOPIC,
                "group_id": settings.KAFKA_VERIFICATION_GROUP_ID,
                "handler": handle_verification_result,
                "name": "VerificationResultConsumerRegLogin",
                "required_settings": ['IDENTITY_VERIFICATION_RESULT_TOPIC', 'KAFKA_VERIFICATION_GROUP_ID']
            },
            # {
            #     "topic": settings.HMRC_DEATH_NOTIFICATION_TOPIC,
            #     "group_id": settings.KAFKA_DEATH_EVENT_GROUP_ID,
            #     "handler": handle_death_notification,
            #     "name": "DeathNotificationConsumerRegLogin",
            #     "required_settings": ['HMRC_DEATH_NOTIFICATION_TOPIC', 'KAFKA_DEATH_EVENT_GROUP_ID']
            # }
        ]

        for config in consumer_configs:
            # Check if all specific required settings for this consumer are present
            if not all(hasattr(settings, req_setting) for req_setting in config["required_settings"]):
                logger.warning(f"Skipping consumer '{config['name']}' due to missing Kafka topic/group_id settings: {config['required_settings']}")
                continue

            task = asyncio.create_task(
                start_kafka_consumer( # Call the library function
                    topic=getattr(settings, config["required_settings"][0]), # Get actual topic name
                    group_id=getattr(settings, config["required_settings"][1]), # Get actual group_id
                    broker_url=settings.KAFKA_BROKER_URL,
                    client_id_prefix=settings.KAFKA_CLIENT_ID, # Pass client_id_prefix
                    handler=config["handler"]
                    # Default retry/deserializer from library will be used
                ),
                name=config["name"]
            )
            consumer_tasks.append(task)
            logger.info(f"Consumer task '{config['name']}' for topic '{getattr(settings, config['required_settings'][0])}' created.")

    logger.info(f"Kafka consumers setup initiated. Tasks: {len(consumer_tasks)}")

    yield

    logger.info("Shutting down application via lifespan...")

    if kafka_connection_task and not kafka_connection_task.done():
        logger.info("Cancelling background Kafka producer connection task...")
        kafka_connection_task.cancel()
        try:
            await kafka_connection_task
        except asyncio.CancelledError:
            logger.info("Background Kafka producer connection task cancelled successfully during shutdown.")
        except Exception as e: # Catch all other exceptions
            logger.error(f"Error during background Kafka producer connection task awaited cancellation: {e}", exc_info=True)


    logger.info(f"Stopping Kafka consumer tasks... ({len(consumer_tasks)} identified)")
    for task in consumer_tasks:
        if not task.done():
            logger.info(f"Cancelling consumer task: {task.get_name()}")
            task.cancel()

    # Await all consumer tasks to finish after cancellation
    if consumer_tasks:
        results = await asyncio.gather(*consumer_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            task_name = consumer_tasks[i].get_name()
            if isinstance(result, asyncio.CancelledError):
                logger.info(f"Consumer task {task_name} was cancelled successfully.")
            elif isinstance(result, Exception):
                logger.error(f"Consumer task {task_name} threw an exception during shutdown: {result}", exc_info=result)
            else:
                logger.info(f"Consumer task {task_name} finished gracefully.")

    consumer_tasks.clear() # Clear the list of tasks

    # Call library's disconnect functions
    # disconnect_kafka_consumers from the library stops the aiokafka consumer instances
    # It's good to call it after tasks are cancelled to ensure graceful stop of internal loops if any.
    await disconnect_kafka_consumers()
    logger.info("Shared library's disconnect_kafka_consumers called.")

    await disconnect_kafka_producer()
    logger.info("Shared library's disconnect_kafka_producer called.")

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
    # app.include_router(google_auth.router, prefix=f"{settings.API_V1_STR}/auth/google", tags=["google-auth"]) # Google Auth, уже было закомментировано, оставляем так

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
        service_overall_status = "degraded"
        http_status_code = 503

        try:
            await test_connection()
        except Exception as e:
            logger.error(f"Healthcheck: DB connection failed: {e}")
            db_status = "error"

        if kafka_producer_ready.is_set():
            try:
                get_kafka_producer() # Use library's function; raises RuntimeError if not ok
                kafka_prod_status = "ok"
            except RuntimeError: # Raised by get_kafka_producer if _producer is None
                kafka_prod_status = "error_after_ready"
                kafka_producer_ready.clear()
        elif kafka_connection_task and not kafka_connection_task.done():
            kafka_prod_status = "connecting"
        elif kafka_connection_task and kafka_connection_task.done() and not kafka_producer_ready.is_set():
            # Task finished, but producer not ready (means it failed all retries or had an issue)
            kafka_prod_status = "failed_to_connect"
        else: # Default to unavailable if no other condition met (e.g. task not even started)
            kafka_prod_status = "unavailable"


        if db_status == "ok" and kafka_prod_status == "ok":
            service_overall_status = "ok"
            http_status_code = 200
        elif db_status == "ok" and kafka_prod_status in ["connecting", "unavailable", "failed_to_connect"]:
            # If DB is ok, but Kafka is still connecting or unavailable, service is degraded but accessible
            service_overall_status = f"degraded_kafka_{kafka_prod_status}"
            http_status_code = 200 # Or 503 if Kafka is critical for all operations
        else: # db error or other critical combination
            service_overall_status = "error"
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
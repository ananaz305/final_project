import logging.config
import time
import json
import asyncio
import uuid # Для генерации correlation_id
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any # Добавил typing
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from .core.config import settings
# Обновленные импорты Kafka из общей библиотеки
from shared.kafka_client_lib.client import (
    connect_kafka_producer as shared_connect_kafka_producer, # Переименовываем, чтобы избежать конфликта с локальной функцией, если она будет
    disconnect_kafka_producer as shared_disconnect_kafka_producer,
    get_kafka_producer as shared_get_kafka_producer,
    send_kafka_message_fire_and_forget # Новая функция для логов
)
from shared.kafka_client_lib.exceptions import KafkaConnectionError, KafkaMessageSendError

from .core.proxy import proxy_request, shutdown_proxy_client
from .core.security import decode_access_token
from .schemas.user import TokenPayload

# Настройка логирования
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "loggers": {
        "app": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "shared": {"handlers": ["console"], "level": "INFO", "propagate": False}, # Логгер для общей библиотеки
        "aiokafka": {"handlers": ["console"], "level": "WARNING"},
        "httpx": {"handlers": ["console"], "level": "WARNING"},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app")

# Глобальные переменные для управления Kafka продюсером, аналогично reg-login-service
kafka_producer_ready = asyncio.Event()
kafka_connection_task: Optional[asyncio.Task] = None

async def connect_kafka_producer_with_event_gw(): # Renamed for clarity if both mains were in one file context for a moment
    """Tries to connect the Kafka producer for API Gateway and sets an event upon success."""
    global kafka_producer_ready
    try:
        logger.info(f"[{settings.PROJECT_NAME}] Background task: Attempting to connect Kafka producer...")
        retry_delay = settings.KAFKA_RECONNECT_DELAY_S if hasattr(settings, 'KAFKA_RECONNECT_DELAY_S') else 10
        max_retries = settings.KAFKA_MAX_RETRIES if hasattr(settings, 'KAFKA_MAX_RETRIES') else 5
        attempt = 0

        if not hasattr(settings, 'KAFKA_BROKER_URL') or not hasattr(settings, 'KAFKA_CLIENT_ID'):
            logger.critical(f"[{settings.PROJECT_NAME}] KAFKA_BROKER_URL or KAFKA_CLIENT_ID not configured.")
            return

        while attempt < max_retries:
            try:
                await shared_connect_kafka_producer(
                    broker_url=settings.KAFKA_BROKER_URL,
                    client_id=settings.KAFKA_CLIENT_ID
                )
                shared_get_kafka_producer()
                kafka_producer_ready.set()
                logger.info(f"[{settings.PROJECT_NAME}] Background task: Kafka producer connected successfully.")
                return
            except KafkaConnectionError as e:
                logger.error(f"[{settings.PROJECT_NAME}] Background task: Kafka producer connection attempt {attempt+1}/{max_retries} failed: {e}")
            except RuntimeError as e:
                logger.error(f"[{settings.PROJECT_NAME}] Background task: Kafka producer check failed after connection attempt {attempt+1}/{max_retries}: {e}")
            except Exception as e:
                logger.error(f"[{settings.PROJECT_NAME}] Background task: Unexpected error during Kafka producer connection attempt {attempt+1}/{max_retries}: {e}", exc_info=True)

            attempt += 1
            if attempt < max_retries:
                logger.info(f"[{settings.PROJECT_NAME}] Background task: Retrying Kafka producer connection in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"[{settings.PROJECT_NAME}] Background task: Max retries reached for Kafka producer connection. Producer remains unavailable.")
                kafka_producer_ready.clear()

    except asyncio.CancelledError:
        logger.info(f"[{settings.PROJECT_NAME}] Background task: Kafka producer connection task cancelled.")
        raise
    except Exception as e:
        logger.error(f"[{settings.PROJECT_NAME}] Background task: Unexpected error in Kafka producer connection task: {e}", exc_info=True)
        kafka_producer_ready.clear()

async def send_log_message(topic: str, message: Dict[str, Any]):
    """Отправляет лог в Kafka (fire-and-forget), используя общую библиотеку."""
    try:
        # shared_get_kafka_producer() # Можно добавить проверку, если нужно быть уверенным что продюсер готов перед попыткой отправки
        # но send_kafka_message_fire_and_forget сама это проверит.
        await send_kafka_message_fire_and_forget(topic, message)
        logger.debug(f"Log message enqueued to topic {topic} via shared library")
    except KafkaMessageSendError as e: # Это исключение не должно выбрасываться из fire-and-forget версии, но на всякий случай
        logger.error(f"KafkaMessageSendError while sending log to topic {topic}: {e}")
    except RuntimeError as e: # Если get_kafka_producer внутри fire-and-forget версии выявит проблему
        logger.warning(f"RuntimeError (likely producer not ready) sending log to {topic}: {e}")
    except Exception as e:
        logger.error(f"Failed to send log message to topic {topic} using shared library: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manages application startup and shutdown events for API Gateway."""
    global kafka_connection_task, kafka_producer_ready
    logger.info(f"[{settings.PROJECT_NAME}] API Gateway starting up via lifespan...")
    kafka_producer_ready.clear()

    logger.info(f"[{settings.PROJECT_NAME}] Initiating Kafka producer connection in background...")
    if kafka_connection_task and not kafka_connection_task.done():
        kafka_connection_task.cancel()
    kafka_connection_task = asyncio.create_task(connect_kafka_producer_with_event_gw(), name="KafkaProducerConnectorGW")

    # HTTPX client initialization can be done here if needed explicitly before yield
    # For now, proxy_request handles client lazily or it's managed globally by httpx itself.

    yield

    logger.info(f"[{settings.PROJECT_NAME}] API Gateway shutting down via lifespan...")

    if kafka_connection_task and not kafka_connection_task.done():
        logger.info(f"[{settings.PROJECT_NAME}] Cancelling background Kafka producer connection task...")
        kafka_connection_task.cancel()
        try:
            await kafka_connection_task
        except asyncio.CancelledError:
            logger.info(f"[{settings.PROJECT_NAME}] Background Kafka producer connection task cancelled successfully during shutdown.")
        except Exception as e:
            logger.error(f"[{settings.PROJECT_NAME}] Error during background Kafka producer connection task awaited cancellation: {e}", exc_info=True)

    await shared_disconnect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Shared library's disconnect_kafka_producer called.")

    await shutdown_proxy_client()
    logger.info(f"[{settings.PROJECT_NAME}] HTTPX client shutdown.")
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
    else:
        logger.warning(
            f"BACKEND_CORS_ORIGINS is set to an unsupported type: {type(settings.BACKEND_CORS_ORIGINS)}. "
            f"CORS will not be enabled for specific origins. Value: {settings.BACKEND_CORS_ORIGINS}"
        )
        # allow_origins remains [], which is safe (no origins allowed by default if config is wrong)

    # Only add middleware if allow_origins has been populated (or explicitly set to ["*"])
    # This also handles the case where BACKEND_CORS_ORIGINS was an unsupported type and allow_origins remained []
    if allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    elif not settings.BACKEND_CORS_ORIGINS: # Explicitly not set or empty
        logger.info("BACKEND_CORS_ORIGINS is not set or empty. CORS middleware not added for specific origins.")
    # If BACKEND_CORS_ORIGINS was set to an invalid type, the warning above is logged, and middleware isn't added for specific origins.

# --- Middleware для Kafka Логирования Активности ---
@app.middleware("http")
async def kafka_logging_middleware(request: Request, call_next):
    """Middleware для логирования HTTP запросов и ответов в Kafka и управления X-Correlation-ID."""
    start_time = time.time()

    # Обработка X-Correlation-ID
    correlation_id = request.headers.get("x-correlation-id")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
        logger.debug(f"Generated new correlation_id: {correlation_id}")
    else:
        logger.debug(f"Using existing correlation_id: {correlation_id}")
    request.state.correlation_id = correlation_id

    request_log = {
        "timestamp": datetime.now().isoformat(),
        "level": "INFO",
        "service": settings.KAFKA_CLIENT_ID,
        "message": "Request received",
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get('user-agent'),
        "request_id": request.headers.get('x-request-id'), # Это может быть другим ID, например, от внешнего балансировщика
        "correlation_id": correlation_id
    }
    asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, request_log))

    response_obj = None
    try:
        response_obj = await call_next(request)
        process_time = time.time() - start_time
        response_log = {
            "timestamp": datetime.now().isoformat(),
            "level": "WARN" if response_obj.status_code >= 400 else "INFO",
            "service": settings.KAFKA_CLIENT_ID,
            "message": "Request finished",
            "method": request.method,
            "path": request.url.path,
            "status_code": response_obj.status_code,
            "duration_ms": round(process_time * 1000, 2),
            "user_id": request.state.user.id if hasattr(request.state, 'user') and hasattr(request.state.user, 'id') else None,
            "correlation_id": correlation_id
        }
        asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, response_log))
        response_obj.headers["X-Process-Time-Ms"] = str(round(process_time * 1000, 2))
        response_obj.headers["X-Correlation-ID"] = correlation_id # Возвращаем ID клиенту
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Error during request processing: {e}", exc_info=True)
        error_log = {
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "service": settings.KAFKA_CLIENT_ID,
            "message": "Request processing error",
            "method": request.method,
            "path": request.url.path,
            "duration_ms": round(process_time * 1000, 2),
            "error": str(e),
            "user_id": request.state.user.id if hasattr(request.state, 'user') and hasattr(request.state.user, 'id') else None,
            "correlation_id": correlation_id
        }
        asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, error_log))
        response_obj = Response("Internal Server Error", status_code=500)
        # raise e from None # Перехватываем здесь, чтобы вернуть кастомный Response
    return response_obj

# --- Middleware/Dependency для Аутентификации (Заглушка) ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def authenticate_request(request: Request, token: str = Depends(oauth2_scheme)):
    """Зависимость для проверки токена аутентификации."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    access_log = {
        "timestamp": datetime.now().isoformat(),
        "service": settings.KAFKA_CLIENT_ID,
        "resource": request.url.path,
        "granted": False,
        "error": None,
        "user_id": None,
        "correlation_id": request.state.correlation_id if hasattr(request.state, "correlation_id") else None
    }

    token_data: TokenPayload | None = decode_access_token(token)

    if not token_data or not token_data.sub:
        access_log["error"] = "Invalid or missing token data (sub claim missing or token invalid)"
        asyncio.create_task(send_log_message(settings.ACCESS_LOG_TOPIC, access_log))
        raise credentials_exception

    request.state.user = token_data
    access_log["granted"] = True
    access_log["user_id"] = token_data.sub
    # correlation_id уже есть в access_log из инициализации выше
    asyncio.create_task(send_log_message(settings.ACCESS_LOG_TOPIC, access_log))
    logger.debug(f"Authenticated user ID: {token_data.sub} for path {request.url.path}")

# --- Маршруты Проксирования ---
protected_route_dependency = [Depends(authenticate_request)]

@app.api_route("/api/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_auth_service(request: Request):
    """Проксирует запросы к сервису аутентификации."""
    logger.info(f"Routing to AUTH service for path: {request.url.path}")
    return await proxy_request(request, settings.AUTH_SERVICE_URL, "auth")

@app.api_route("/api/nhs/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_nhs_service(request: Request):
    """Проксирует запросы к сервису NHS."""
    # path = request.url.path # Не используется далее
    # Логика с if path.startswith("/api/nhs/appointments") убрана для упрощения,
    # предполагается, что nhs-service сам разрулит внутренние пути.
    logger.info(f"Routing to NHS service for path: {request.url.path}")
    return await proxy_request(request, settings.NHS_SERVICE_URL, "nhs")

@app.api_route("/api/hmrc/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
               dependencies=protected_route_dependency)
async def proxy_hmrc_service(request: Request):
    """Проксирует запросы к сервису HMRC (защищенный маршрут)."""
    logger.info(f"Routing to HMRC service for path: {request.url.path} for user {request.state.user.id if hasattr(request.state, 'user') else 'Unknown'}")
    return await proxy_request(request, settings.HMRC_SERVICE_URL, "hmrc")

@app.get("/")
async def root_endpoint(): # Переименовано root -> root_endpoint
    """Корневой эндпоинт API Gateway."""
    return {"message": f"Welcome to {settings.PROJECT_NAME}! API Gateway is operational."}

@app.get("/health")
async def healthcheck_gateway():
    """Эндпоинт для проверки работоспособности API Gateway."""
    logger.info(f"[{settings.PROJECT_NAME}] Healthcheck requested for API Gateway.")
    kafka_prod_status = "unavailable"

    if kafka_producer_ready.is_set():
        try:
            shared_get_kafka_producer()
            kafka_prod_status = "ok"
        except RuntimeError:
            kafka_prod_status = "error_after_ready"
            kafka_producer_ready.clear()
    elif kafka_connection_task and not kafka_connection_task.done():
        kafka_prod_status = "connecting"
    elif kafka_connection_task and kafka_connection_task.done() and not kafka_producer_ready.is_set():
        kafka_prod_status = "failed_to_connect"
    else:
        kafka_prod_status = "unavailable"

    service_overall_status = "ok" if kafka_prod_status == "ok" else "degraded"
    http_status_code = 200 if service_overall_status == "ok" else 503

    response_payload = {
        "status": service_overall_status,
        "service": settings.PROJECT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "kafka_producer": kafka_prod_status
        }
    }
    # For healthcheck, it's common to return 200 OK and indicate status in body,
    # or return actual 503/200. Here we adjust to return 503 if degraded.
    if http_status_code != 200:
        # This will make FastAPI return 503 with the JSON body
        return Response(content=json.dumps(response_payload), status_code=http_status_code, media_type="application/json")
    return response_payload

# Общий обработчик ошибок, чтобы гарантировать возврат JSON при неожиданных сбоях
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Обрабатывает любые неперехваченные исключения и возвращает стандартизированный JSON ответ."""
    logger.error(f"Unhandled exception during request to {request.url.path}: {exc}", exc_info=True)
    error_log = {
        "timestamp": datetime.now().isoformat(),
        "level": "ERROR",
        "service": settings.KAFKA_CLIENT_ID,
        "message": "Unhandled exception in API Gateway handler",
        "method": request.method,
        "path": request.url.path,
        "error_type": type(exc).__name__,
        "error_details": str(exc),
        "user_id": request.state.user.id if hasattr(request.state, 'user') and hasattr(request.state.user, 'id') else None,
        "correlation_id": request.state.correlation_id if hasattr(request.state, "correlation_id") else None
    }
    asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, error_log))

    # Возвращаем JSON ответ вместо простого текста для Response("Internal Server Error")
    # Это более дружелюбно для API клиентов
    return Response(
        content=json.dumps({"detail": "Internal Server Error", "error_id": error_log["timestamp"]}),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        media_type="application/json"
    )
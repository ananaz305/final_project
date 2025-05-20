import logging.config
import time
import json
import asyncio
import uuid # Для генерации correlation_id
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from .core.config import settings
from .kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    send_log_message,
    get_kafka_producer
)
from .core.proxy import proxy_request, shutdown_proxy_client
from .core.security_stub import decode_access_token, TokenPayload

# Настройка логирования
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "loggers": {
        "app": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "aiokafka": {"handlers": ["console"], "level": "WARNING"},
        "httpx": {"handlers": ["console"], "level": "WARNING"}, # Уменьшаем шум от httpx
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Управляет жизненным циклом Kafka producer и HTTPX client."""
    logger.info(f"[{settings.PROJECT_NAME}] API Gateway starting up via lifespan...")
    await connect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Kafka producer connected.")
    # Здесь может быть инициализация HTTPX клиента, если она вынесена в отдельную функцию
    yield
    logger.info(f"[{settings.PROJECT_NAME}] API Gateway shutting down via lifespan...")
    await disconnect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Kafka producer disconnected.")
    await shutdown_proxy_client() # Закрываем httpx клиент
    logger.info(f"[{settings.PROJECT_NAME}] HTTPX client shutdown.")
    logger.info(f"[{settings.PROJECT_NAME}] Lifespan shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan # Используем lifespan
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

    if not token_data or not token_data.id:
        access_log["error"] = "Invalid or missing token data"
        asyncio.create_task(send_log_message(settings.ACCESS_LOG_TOPIC, access_log))
        raise credentials_exception

    request.state.user = token_data
    access_log["granted"] = True
    access_log["user_id"] = token_data.id
    # correlation_id уже есть в access_log из инициализации выше
    asyncio.create_task(send_log_message(settings.ACCESS_LOG_TOPIC, access_log))
    logger.debug(f"Authenticated user ID: {token_data.id} for path {request.url.path}")

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

@app.get("/health") # Простой путь для healthcheck шлюза
async def healthcheck_gateway():
    """Эндпоинт для проверки работоспособности API Gateway."""
    logger.info(f"[{settings.PROJECT_NAME}] Healthcheck requested.")
    kafka_status = "ok"
    try:
        # Проверяем, что Kafka producer доступен (был инициализирован в lifespan)
        # Это косвенная проверка, т.к. connect_kafka_producer выполняется при старте.
        # Для более надежной проверки можно было бы иметь функцию ping в kafka.client
        if not get_kafka_producer(): # Если продюсер None после старта
            kafka_status = "producer_not_initialized_or_failed"
        # Можно добавить проверку типа producer.partitions_for(test_topic),
        # но это дольше и может требовать существования топика.
    except RuntimeError: # Если get_kafka_producer выбрасывает RuntimeError (producer is None)
        kafka_status = "producer_not_initialized"
    except Exception as e:
        logger.error(f"Healthcheck: Kafka check failed for API Gateway: {e}")
        kafka_status = "error"

    return {
        "status": "ok" if kafka_status == "ok" else "degraded",
        "service": settings.PROJECT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(), # Убедимся, что datetime и timezone импортированы
        "dependencies": {
            "kafka_producer": kafka_status
        }
    }

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
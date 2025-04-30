import logging
import logging.config
import time
import json
from datetime import datetime
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.kafka.client import (
    connect_kafka_producer,
    disconnect_kafka_producer,
    send_log_message
)
from app.core.proxy import proxy_request, shutdown_proxy_client
# Заглушка для декодирования токена (позже заменить на Keycloak)
from app.core.security_stub import decode_access_token, TokenPayload

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

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# --- Обработчики событий Startup/Shutdown ---
@app.on_event("startup")
async def startup_event():
    logger.info(f"[{settings.PROJECT_NAME}] Starting up...")
    await connect_kafka_producer()
    logger.info(f"[{settings.PROJECT_NAME}] Startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"[{settings.PROJECT_NAME}] Shutting down...")
    await disconnect_kafka_producer()
    await shutdown_proxy_client() # Закрываем httpx клиент
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

# --- Middleware для Kafka Логирования Активности ---
@app.middleware("http")
async def kafka_logging_middleware(request: Request, call_next):
    start_time = time.time()
    # Не логируем тело запроса/ответа по умолчанию (может быть большим)
    request_log = {
        "timestamp": datetime.now().isoformat(),
        "level": "INFO",
        "service": settings.KAFKA_CLIENT_ID,
        "message": "Request received",
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "client_ip": request.client.host,
        "user_agent": request.headers.get('user-agent'),
        "request_id": request.headers.get('x-request-id') # Если есть
    }
    await send_log_message(settings.ACTIVITY_LOG_TOPIC, request_log)

    response = None
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response_log = {
            "timestamp": datetime.now().isoformat(),
            "level": "WARN" if response.status_code >= 400 else "INFO",
            "service": settings.KAFKA_CLIENT_ID,
            "message": "Request finished",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(process_time * 1000, 2),
            "user_id": request.state.user.id if hasattr(request.state, 'user') and request.state.user else None
        }
        # Не ждем отправки лога ответа
        asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, response_log))
        response.headers["X-Process-Time-Ms"] = str(round(process_time * 1000, 2)) # Добавляем заголовок времени обработки
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
            "user_id": request.state.user.id if hasattr(request.state, 'user') and request.state.user else None
        }
        asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, error_log))
        # Важно вернуть стандартный ответ об ошибке
        response = Response("Internal Server Error", status_code=500)
        # Поднимаем исключение дальше, чтобы стандартный обработчик ошибок FastAPI сработал
        raise e from None

    return response

# --- Middleware/Dependency для Аутентификации (Заглушка) ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login") # Указываем путь внутри шлюза

async def authenticate_request(request: Request, token: str = Depends(oauth2_scheme)):
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
        "user_id": None
    }

    token_data: TokenPayload | None = decode_access_token(token)

    if not token_data or not token_data.id:
        access_log["error"] = "Invalid or missing token data"
        asyncio.create_task(send_log_message(settings.ACCESS_LOG_TOPIC, access_log))
        raise credentials_exception

    # Здесь можно добавить проверку статуса пользователя (blocked и т.д.), если нужно на уровне шлюза
    # if token_data.status == "blocked": ...

    # Сохраняем информацию о пользователе в состоянии запроса для логирования и возможной авторизации
    request.state.user = token_data
    access_log["granted"] = True
    access_log["user_id"] = token_data.id
    asyncio.create_task(send_log_message(settings.ACCESS_LOG_TOPIC, access_log))
    logger.debug(f"Authenticated user ID: {token_data.id}")
    # Не возвращаем ничего, зависимость просто проверяет токен

# --- Маршруты Проксирования ---
# Защищенные маршруты требуют аутентификации
protected_route_dependency = [Depends(authenticate_request)]

@app.api_route("/api/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_auth(request: Request):
    return await proxy_request(request, settings.REG_LOGIN_SERVICE_URL, "auth")

@app.api_route("/api/nns/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
               dependencies=protected_route_dependency)
async def proxy_nns(request: Request):
    # Проверяем путь запроса
    # Для /api/nns/appointments используем новый эндпоинт
    # Для старых (если они остались) - старый
    # TODO: Улучшить маршрутизацию, если путей будет много
    if "/appointments" in request.url.path:
        # Здесь можно добавить проверку ролей/статуса из request.state.user
        # Например, разрешить запись только верифицированным пользователям
        # if request.state.user.status != 'verified':
        #     raise HTTPException(status_code=403, detail="User must be verified to book appointments")
        logger.info("Routing to /appointments endpoint in NNS service")
        # Проксируем на конкретный эндпоинт (или весь сервис, как сейчас)
        return await proxy_request(request, settings.NNS_SERVICE_URL, "nns")
    else:
        # Проксируем остальные запросы к /api/nns/* (если такие есть)
        logger.info("Routing other /api/nns request to NNS service")
        return await proxy_request(request, settings.NNS_SERVICE_URL, "nns")

@app.api_route("/api/hmrc/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
               dependencies=protected_route_dependency)
async def proxy_hmrc(request: Request):
    # if request.state.user.status != 'verified': ...
    return await proxy_request(request, settings.HMRC_SERVICE_URL, "hmrc")

# Корневой эндпоинт шлюза
@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}!"}

# Добавляем обработчик ошибок сервера (ловим исключения после middleware)
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception during request to {request.url.path}: {exc}", exc_info=True)
    # Дополнительное логирование ошибки, если она не была поймана middleware
    error_log = {
        "timestamp": datetime.now().isoformat(),
        "level": "ERROR",
        "service": settings.KAFKA_CLIENT_ID,
        "message": "Unhandled exception in handler",
        "method": request.method,
        "path": request.url.path,
        "error": str(exc),
        "user_id": request.state.user.id if hasattr(request.state, 'user') and request.state.user else None
    }
    # Запускаем отправку лога, но не ждем ее
    asyncio.create_task(send_log_message(settings.ACTIVITY_LOG_TOPIC, error_log))
    return Response("Internal Server Error", status_code=500)
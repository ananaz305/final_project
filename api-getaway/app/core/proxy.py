import logging
import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from typing import Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Создаем один httpx клиент для переиспользования соединений
# Важно настроить таймауты
client = httpx.AsyncClient(timeout=settings.SERVICE_TIMEOUT)

# Заголовки, которые не следует проксировать напрямую
# (например, связанные с кодировкой или hop-by-hop заголовки)
EXCLUDED_HEADERS = [
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
    "host" # Host будет установлен httpx
]

async def proxy_request(
        request: Request,
        target_url: str,
        service_name: str # Для логирования
) -> Response:
    """Проксирует входящий запрос на указанный target_url."""

    # Формируем URL для downstream-сервиса
    downstream_path = request.url.path.split(settings.API_V1_STR, 1)[-1] # Убираем префикс API Gateway
    # Убираем префикс конкретного сервиса (например, /auth, /nhs)
    service_prefix = f"/{service_name.lower()}"
    if downstream_path.startswith(service_prefix):
        downstream_path = downstream_path[len(service_prefix):]

    target = f"{target_url}{downstream_path}"
    if request.url.query:
        target += f"?{request.url.query}"

    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Proxying request {request.method} {request.url.path} to {target}")

    # Копируем заголовки, исключая ненужные
    headers = {k: v for k, v in request.headers.items() if k.lower() not in EXCLUDED_HEADERS}

    # Добавляем информацию о проксировании (опционально)
    # headers["X-Forwarded-For"] = request.client.host
    # headers["X-Forwarded-Proto"] = request.url.scheme

    # Получаем тело запроса (если есть)
    # Используем request.stream() для поддержки больших тел запросов
    req_content = request.stream()

    # Копируем тело запроса, если оно есть и метод не GET/HEAD
    # Это важно для POST, PUT, PATCH
    # TODO: Оценить нужность условия `if content_length and content_length > "0":` - возможно, лучше проверять метод
    # Текущая реализация FastAPI/Starlette может автоматически обрабатывать пустое тело для POST
    # try:
    #     # Пытаемся получить тело как json, если не получается - как байты
    #     # Это более универсально, но может быть медленнее
    #     # request_data = await request.json() if request.method not in ["GET", "DELETE", "HEAD"] else None
    #     # logger.debug(f"Request JSON data: {request_data}")
    #     request_data_bytes = await request.body()
    #     logger.debug(f"Request body bytes length: {len(request_data_bytes)}")
    # except Exception as e:
    #     logger.warning(f"Could not parse request body as JSON: {e}")
    #     request_data_bytes = await request.body()
    #     # request_data = None # или оставить как байты, если downstream сервис это ожидает

    request_data_bytes = await request.body()

    # Создаем запрос к downstream-сервису
    try:
        proxy_req = client.build_request(
            method=request.method,
            url=target,
            headers=headers,
            content=req_content,
            # timeout=settings.SERVICE_TIMEOUT # Таймаут установлен на клиенте
        )

        # Отправляем запрос и получаем ответ
        proxy_resp = await client.send(proxy_req, stream=True)

        # Обрабатываем ответ
        resp_headers = {k: v for k, v in proxy_resp.headers.items() if k.lower() not in EXCLUDED_HEADERS}

        # Создаем BackgroundTask для закрытия ответа после его отправки клиенту
        task = BackgroundTask(proxy_resp.aclose)

        # Возвращаем StreamingResponse, чтобы не загружать все тело ответа в память
        logger.info(f"[{settings.KAFKA_CLIENT_ID}] Received {proxy_resp.status_code} from {target}")
        return StreamingResponse(
            proxy_resp.aiter_raw(),
            status_code=proxy_resp.status_code,
            headers=resp_headers,
            background=task,
            media_type=proxy_resp.headers.get("content-type")
        )

    except httpx.TimeoutException:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Timeout error when proxying to {target}")
        return Response(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content=f"Upstream service {service_name} timeout")
    except httpx.ConnectError:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Connection error when proxying to {target}")
        return Response(status_code=status.HTTP_502_BAD_GATEWAY, content=f"Upstream service {service_name} connection error")
    except Exception as e:
        logger.error(f"[{settings.KAFKA_CLIENT_ID}] Unexpected error during proxy request to {target}: {e}", exc_info=True)
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content="Internal proxy error")

async def shutdown_proxy_client():
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Closing httpx client...")
    await client.aclose()
    logger.info(f"[{settings.KAFKA_CLIENT_ID}] httpx client closed.")
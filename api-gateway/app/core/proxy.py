import logging
import httpx
from fastapi import Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from typing import Dict, Any, Optional
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

# Creating single http client
client = httpx.AsyncClient(timeout=settings.SERVICE_TIMEOUT)

# Headers, which we are not proxying
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
    "host"
]

async def proxy_request(
        request: Request,
        target_url: str,
        service_name: str
) -> Response:
    """Proxying to target_url."""

    # Creating url for downstream service
    downstream_path = request.url.path.split(settings.API_V1_STR, 1)[-1]
    # Removing prefix of required service (ex.: /auth, /nhs)
    service_prefix = f"/{service_name.lower()}"
    if downstream_path.startswith(service_prefix):
        downstream_path = downstream_path[len(service_prefix):]

    target = f"{target_url}{downstream_path}"
    if request.url.query:
        target += f"?{request.url.query}"

    logger.info(f"[{settings.KAFKA_CLIENT_ID}] Proxying request {request.method} {request.url.path} to {target}")

    # Copying headers
    headers = {k: v for k, v in request.headers.items() if k.lower() not in EXCLUDED_HEADERS}

    # Adding X-Correlation-ID, if it exist in request.state
    if hasattr(request.state, "correlation_id") and request.state.correlation_id:
        headers["x-correlation-id"] = request.state.correlation_id
        logger.debug(f"Proxying with X-Correlation-ID: {request.state.correlation_id}")
    else:
        # We could create own id, if it wasn't set in the middleware
        # but this should not happen when working properly.

        # temp_correlation_id = str(uuid.uuid4())
        # headers["x-correlation-id"] = temp_correlation_id
        logger.warning("X-Correlation-ID not found in request.state for proxying.")

    # Getting request body
    req_content = request.stream()

    # Copying req_body to new request
    # TODO: Evaluate the condition `if content_length and content_length > "0":` - perhaps it is better to check the method
    # The current FastAPI/Starlette implementation can automatically process an empty body for a POST
    # try:
    # # We are trying to get the body as json, if it does not work out, as bytes
    #     # It's more versatile, but it can be slower
    #     # request_data = await request.json() if request.method not in ["GET", "DELETE", "HEAD"] else None
    #     # logger.debug(f"Request JSON data: {request_data}")
    #     request_data_bytes = await request.body()
    #     logger.debug(f"Request body bytes length: {len(request_data_bytes)}")
    # except Exception as e:
    #     logger.warning(f"Could not parse request body as JSON: {e}")
    #     request_data_bytes = await request.body()
    # # request_data = None # or leave as bytes if the downstream service expects it.

    # request_data_bytes = await request.body() # This line is not used, the req_content is already there.

    # Creating final request
    try:
        proxy_req = client.build_request(
            method=request.method,
            url=target,
            headers=headers,
            content=req_content,
        )

        # Sending request and getting response
        proxy_resp = await client.send(proxy_req, stream=True)

        # Removing headers from response
        resp_headers = {k: v for k, v in proxy_resp.headers.items() if k.lower() not in EXCLUDED_HEADERS}

        # Creating a background task for client responding
        task = BackgroundTask(proxy_resp.aclose)

        # Returning StreamingResponse for not loading full body copy in memory
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
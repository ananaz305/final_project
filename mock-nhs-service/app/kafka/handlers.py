import logging
from ..services.nhs_service import (
    process_book_appointment,
    process_get_visit_status,
    process_cancel_appointment
)
from .producer import send_nhs_response
from ..schemas.nhs_schemas import NHSRequest, RequestType  # Создадим эти схемы позже

logger = logging.getLogger(__name__)

async def handle_nhs_request(request_data: dict):
    logger.info(f"Handling NHS request: {request_data}")
    try:
        # Валидация входящего запроса с использованием Pydantic схемы
        # Это пример, вам нужно будет определить схему NHSRequest
        nhs_request = NHSRequest(**request_data)

        correlation_id = nhs_request.metadata.get("correlation_id") # Предполагаем, что ID корреляции есть в метаданных
        response_payload = None
        error_occurred = False

        if nhs_request.request_type == RequestType.BOOK_APPOINTMENT:
            response_payload = await process_book_appointment(nhs_request.payload)
        elif nhs_request.request_type == RequestType.GET_VISIT_STATUS:
            response_payload = await process_get_visit_status(nhs_request.payload)
        elif nhs_request.request_type == RequestType.CANCEL_APPOINTMENT:
            response_payload = await process_cancel_appointment(nhs_request.payload)
        else:
            logger.error(f"Unknown request type: {nhs_request.request_type}")
            response_payload = {"error": "Unknown request type", "request_type": nhs_request.request_type}
            error_occurred = True

        if response_payload:
            # Формируем ответное сообщение
            response_message = {
                "metadata": {
                    "correlation_id": correlation_id, # Возвращаем ID корреляции для связывания запроса и ответа
                    "service_name": "MockNHSService",
                    "status": "error" if error_occurred else "success"
                },
                "payload": response_payload
            }
            await send_nhs_response(message=response_message, key=correlation_id) # Используем correlation_id как ключ для Kafka (опционально)

    except Exception as e: # TODO: Конкретизировать Exception (например, ValidationError от Pydantic)
        logger.exception(f"Error handling NHS request: {request_data}")
        correlation_id = request_data.get("metadata", {}).get("correlation_id", "unknown")
        # Отправка сообщения об ошибке
        error_response = {
            "metadata": {
                "correlation_id": correlation_id,
                "service_name": "MockNHSService",
                "status": "error"
            },
            "payload": {"error": str(e), "details": "Failed to process request"}
        }
        await send_nhs_response(message=error_response, key=correlation_id) 
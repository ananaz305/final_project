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
        # Validation of an incoming request using the Pydantic scheme
        # This is an example, you will need to define the NHSRequest scheme
        nhs_request = NHSRequest(**request_data)

        correlation_id = nhs_request.metadata.get("correlation_id") # We assume that the correlation ID is in the metadata
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
            # Forming a reply message
            response_message = {
                "metadata": {
                    "correlation_id": correlation_id, # Returning the correlation ID to link the request and the response
                    "service_name": "MockNHSService",
                    "status": "error" if error_occurred else "success"
                },
                "payload": response_payload
            }
            await send_nhs_response(message=response_message, key=correlation_id) # Using correlation_id as the key for Kafka (optional)

    except Exception as e: # TODO: Specify an Exception (for example, ValidationError от Pydantic)
        logger.exception(f"Error handling NHS request: {request_data}")
        correlation_id = request_data.get("metadata", {}).get("correlation_id", "unknown")
        # Sending an error message
        error_response = {
            "metadata": {
                "correlation_id": correlation_id,
                "service_name": "MockNHSService",
                "status": "error"
            },
            "payload": {"error": str(e), "details": "Failed to process request"}
        }
        await send_nhs_response(message=error_response, key=correlation_id) 
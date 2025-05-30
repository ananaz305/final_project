import logging
import uuid
from typing import Dict, Any
from datetime import datetime, timedelta

# Import schemas for request payloads and responses
from ..schemas.nhs_schemas import (
    BookAppointmentPayload, GetVisitStatusPayload, CancelAppointmentPayload,
    BookAppointmentResponse, VisitStatusResponse, CancelAppointmentResponse
)

logger = logging.getLogger(__name__)

# Simple in-memory "database" for the mock service
# In a real mock service, this could be more complex logic or even a small database.
mock_appointments_db: Dict[str, Dict[str, Any]] = {}

async def process_book_appointment(payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Processing book appointment: {payload}")
    try:
        # Validate the payload using Pydantic model (if not already done in the handler)
        # book_payload = BookAppointmentPayload(**payload)  # Uncomment if validation is needed here

        appointment_id = str(uuid.uuid4())
        patient_id = payload.get("patient_id")
        doctor_id = payload.get("doctor_id")
        slot_id = payload.get("slot_id")

        # Mock logic: simply store the appointment and return a confirmation
        mock_appointments_db[appointment_id] = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "status": "CONFIRMED",  # or "PENDING" if such logic is needed
            "scheduled_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),  # Approximate time
            "details": payload.get("appointment_details", {})
        }

        response = BookAppointmentResponse(
            appointment_id=appointment_id,
            status="CONFIRMED",
            message="Appointment booked successfully.",
            slot_details={"id": slot_id, "time": mock_appointments_db[appointment_id]["scheduled_time"]}
        )
        return response.model_dump()

    except Exception as e:  # TODO: make Exception more specific (e.g., ValidationError)
        logger.exception("Error in process_book_appointment")
        # Return an error structure according to the response schema, if available
        return BookAppointmentResponse(
            appointment_id="N/A",
            status="FAILED",
            message=str(e)
        ).model_dump()


async def process_get_visit_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Processing get visit status: {payload}")
    try:
        # get_status_payload = GetVisitStatusPayload(**payload)  # Validation
        appointment_id = payload.get("appointment_id")

        appointment_data = mock_appointments_db.get(appointment_id)

        if appointment_data:
            response = VisitStatusResponse(
                appointment_id=appointment_id,
                status=appointment_data.get("status", "UNKNOWN"),
                patient_id=appointment_data.get("patient_id"),
                doctor_id=appointment_data.get("doctor_id"),
                scheduled_time=appointment_data.get("scheduled_time"),
                notes="This is a mock status update."
            )
            return response.model_dump()
        else:
            return VisitStatusResponse(
                appointment_id=appointment_id,
                status="NOT_FOUND",
                message="Appointment not found."
            ).model_dump()

    except Exception as e:
        logger.exception("Error in process_get_visit_status")
        return VisitStatusResponse(
            appointment_id=payload.get("appointment_id", "N/A"),
            status="ERROR",
            message=str(e)
        ).model_dump()

async def process_cancel_appointment(payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Processing cancel appointment: {payload}")
    try:
        # cancel_payload = CancelAppointmentPayload(**payload)  # Validation
        appointment_id = payload.get("appointment_id")

        if appointment_id in mock_appointments_db:
            # Mock logic: change status or remove the entry
            mock_appointments_db[appointment_id]["status"] = "CANCELLED"
            # or: del mock_appointments_db[appointment_id]

            response = CancelAppointmentResponse(
                appointment_id=appointment_id,
                status="CANCELLED_SUCCESS",
                message="Appointment cancelled successfully."
            )
            return response.model_dump()
        else:
            return CancelAppointmentResponse(
                appointment_id=appointment_id,
                status="NOT_FOUND",
                message="Appointment not found, cannot cancel."
            ).model_dump()

    except Exception as e:
        logger.exception("Error in process_cancel_appointment")
        return CancelAppointmentResponse(
            appointment_id=payload.get("appointment_id", "N/A"),
            status="CANCELLED_FAILED",
            message=str(e)
        ).model_dump()

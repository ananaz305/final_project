import logging
import uuid
from typing import Dict, Any
from datetime import datetime, timedelta
# Импортируем схемы для полезной нагрузки запросов и для ответов
from ..schemas.nhs_schemas import (
    BookAppointmentPayload, GetVisitStatusPayload, CancelAppointmentPayload,
    BookAppointmentResponse, VisitStatusResponse, CancelAppointmentResponse
)

logger = logging.getLogger(__name__)

# Простое "хранилище" данных в памяти для mock-сервиса
# В реальном mock-сервисе это может быть более сложная логика или даже небольшая БД.
mock_appointments_db: Dict[str, Dict[str, Any]] = {}

async def process_book_appointment(payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Processing book appointment: {payload}")
    try:
        # Валидируем payload с помощью Pydantic модели (если еще не сделано в handler)
        # book_payload = BookAppointmentPayload(**payload) # Раскомментировать, если валидация нужна здесь

        appointment_id = str(uuid.uuid4())
        patient_id = payload.get("patient_id")
        doctor_id = payload.get("doctor_id")
        slot_id = payload.get("slot_id")

        # Mock-логика: просто сохраняем запись и возвращаем подтверждение
        mock_appointments_db[appointment_id] = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "status": "CONFIRMED", # или "PENDING", если нужна такая логика
            "scheduled_time": (datetime.utcnow() + timedelta(days=1)).isoformat(), # Примерное время
            "details": payload.get("appointment_details", {})
        }

        response = BookAppointmentResponse(
            appointment_id=appointment_id,
            status="CONFIRMED",
            message="Appointment booked successfully.",
            slot_details={"id": slot_id, "time": mock_appointments_db[appointment_id]["scheduled_time"]}
        )
        return response.model_dump()

    except Exception as e: # TODO: конкретизировать Exception (например, ValidationError)
        logger.exception("Error in process_book_appointment")
        # Возвращаем структуру ошибки, соответствующую схеме ответа, если есть
        # или общую ошибку
        return BookAppointmentResponse(
            appointment_id="N/A",
            status="FAILED",
            message=str(e)
        ).model_dump()


async def process_get_visit_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"Processing get visit status: {payload}")
    try:
        # get_status_payload = GetVisitStatusPayload(**payload) # Валидация
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
        # cancel_payload = CancelAppointmentPayload(**payload) # Валидация
        appointment_id = payload.get("appointment_id")

        if appointment_id in mock_appointments_db:
            # Mock-логика: меняем статус или удаляем запись
            mock_appointments_db[appointment_id]["status"] = "CANCELLED"
            # или del mock_appointments_db[appointment_id]

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
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class RequestType(str, Enum):
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    GET_VISIT_STATUS = "GET_VISIT_STATUS"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"

class RequestMetadata(BaseModel):
    correlation_id: str = Field(..., description="Уникальный идентификатор для отслеживания запроса")
    timestamp: str # ISO 8601 timestamp
    # Можно добавить другие метаданные, если необходимо
    # source_service: Optional[str] = None

class NHSRequest(BaseModel):
    request_type: RequestType = Field(..., description="Тип запроса к NHS сервису")
    metadata: RequestMetadata = Field(..., description="Метаданные запроса")
    payload: Dict[str, Any] = Field(..., description="Полезная нагрузка запроса, специфичная для request_type")

# --- Схемы для полезной нагрузки (payload) каждого типа запроса ---

class BookAppointmentPayload(BaseModel):
    patient_id: str = Field(..., description="ID пациента")
    doctor_id: str = Field(..., description="ID врача")
    slot_id: str = Field(..., description="ID временного слота для записи")
    appointment_details: Optional[Dict[str, Any]] = Field(None, description="Дополнительные детали записи")

class GetVisitStatusPayload(BaseModel):
    appointment_id: str = Field(..., description="ID записи к врачу")
    patient_id: Optional[str] = Field(None, description="ID пациента (опционально, для доп. проверки)")

class CancelAppointmentPayload(BaseModel):
    appointment_id: str = Field(..., description="ID записи к врачу для отмены")
    reason: Optional[str] = Field(None, description="Причина отмены")
    patient_id: Optional[str] = Field(None, description="ID пациента (опционально, для доп. проверки)")

# --- Схемы для ответов (payload) ---
# Эти схемы помогут структурировать ответы, которые ваш mock-сервис будет отправлять

class BookAppointmentResponse(BaseModel):
    appointment_id: str
    status: str # e.g., "CONFIRMED", "PENDING", "FAILED"
    message: Optional[str] = None
    slot_details: Optional[Dict[str, Any]] = None

class VisitStatusResponse(BaseModel):
    appointment_id: str
    status: str # e.g., "SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    scheduled_time: Optional[str] = None # ISO 8601 format
    check_in_time: Optional[str] = None # ISO 8601 format
    notes: Optional[str] = None

class CancelAppointmentResponse(BaseModel):
    appointment_id: str
    status: str # e.g., "CANCELLED_SUCCESS", "CANCELLED_FAILED", "NOT_FOUND"
    message: Optional[str] = None 
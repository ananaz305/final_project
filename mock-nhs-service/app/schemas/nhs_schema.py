from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class RequestType(str, Enum):
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    GET_VISIT_STATUS = "GET_VISIT_STATUS"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"

class RequestMetadata(BaseModel):
    correlation_id: str = Field(..., description="Unique identifier for tracking the request")
    timestamp: str  # ISO 8601 timestamp
    # You can add additional metadata if needed
    # source_service: Optional[str] = None

class NHSRequest(BaseModel):
    request_type: RequestType = Field(..., description="Type of request to the NHS service")
    metadata: RequestMetadata = Field(..., description="Request metadata")
    payload: Dict[str, Any] = Field(..., description="Request payload, specific to request_type")

# --- Payload schemas for each type of request ---

class BookAppointmentPayload(BaseModel):
    patient_id: str = Field(..., description="Patient ID")
    doctor_id: str = Field(..., description="Doctor ID")
    slot_id: str = Field(..., description="ID of the time slot for the appointment")
    appointment_details: Optional[Dict[str, Any]] = Field(None, description="Additional appointment details")

class GetVisitStatusPayload(BaseModel):
    appointment_id: str = Field(..., description="Appointment ID")
    patient_id: Optional[str] = Field(None, description="Patient ID (optional, for additional verification)")

class CancelAppointmentPayload(BaseModel):
    appointment_id: str = Field(..., description="Appointment ID to cancel")
    reason: Optional[str] = Field(None, description="Cancellation reason")
    patient_id: Optional[str] = Field(None, description="Patient ID (optional, for additional verification)")

# --- Response schemas (payloads) ---
# These schemas help structure the responses your mock service will send

class BookAppointmentResponse(BaseModel):
    appointment_id: str
    status: str  # e.g., "CONFIRMED", "PENDING", "FAILED"
    message: Optional[str] = None
    slot_details: Optional[Dict[str, Any]] = None

class VisitStatusResponse(BaseModel):
    appointment_id: str
    status: str  # e.g., "SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    scheduled_time: Optional[str] = None  # ISO 8601 format
    check_in_time: Optional[str] = None  # ISO 8601 format
    notes: Optional[str] = None

class CancelAppointmentResponse(BaseModel):
    appointment_id: str
    status: str  # e.g., "CANCELLED_SUCCESS", "CANCELLED_FAILED", "NOT_FOUND"
    message: Optional[str] = None

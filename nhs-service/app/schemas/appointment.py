from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid
from enum import Enum

class AppointmentStatus(str, Enum):
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"

class AppointmentRequest(BaseModel):
    patient_identifier: str = Field(..., description="Patient identifier (e.g., NHS number or internal ID)")
    requested_datetime: datetime
    doctor_specialty: str
    reason: str | None = None

class AppointmentData(BaseModel):
    appointment_id: str = Field(default_factory=uuid.uuid4)
    user_id: str  # ID of the user who initiated the appointment
    patient_identifier: str
    requested_datetime: datetime
    doctor_specialty: str
    reason: str | None = None
    status: AppointmentStatus = AppointmentStatus.REQUESTED
    confirmed_datetime: datetime | None = None
    confirmation_details: str | None = None  # For example, doctor's name, office
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class AppointmentResponse(BaseModel):
    """Response schema for a single appointment."""
    appointment_id: str
    user_id: str
    patient_identifier: str
    requested_datetime: datetime
    doctor_specialty: str
    reason: str | None = None
    status: AppointmentStatus
    confirmed_datetime: datetime | None = None
    confirmation_details: str | None = None
    created_at: datetime
    updated_at: datetime

class KafkaAppointmentRequest(BaseModel):
    """Message sent to Kafka when requesting an appointment."""
    appointment_id: str
    user_id: str
    patient_identifier: str
    requested_datetime: str  # ISO format
    doctor_specialty: str
    reason: Optional[str] = None
    timestamp: str  # ISO format of the sending time
    correlation_id: str  # Added field

class KafkaAppointmentResult(BaseModel):
    """Message with the result of appointment processing (sent to Kafka)."""
    appointment_id: str
    user_id: str
    status: AppointmentStatus
    confirmed_datetime: str | None = None  # ISO format
    confirmation_details: str | None = None
    rejection_reason: str | None = None
    timestamp: str  # ISO format of the sending time

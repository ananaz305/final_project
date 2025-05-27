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
    patient_identifier: str = Field(..., description="Идентификатор пациента (например, NHS номер или внутренний ID)")
    requested_datetime: datetime
    doctor_specialty: str
    reason: str | None = None

class AppointmentData(BaseModel):
    appointment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID # ID пользователя, который инициировал запись
    patient_identifier: str
    requested_datetime: datetime
    doctor_specialty: str
    reason: str | None = None
    status: AppointmentStatus = AppointmentStatus.REQUESTED
    confirmed_datetime: datetime | None = None
    confirmation_details: str | None = None # Например, имя врача, кабинет
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class AppointmentResponse(BaseModel):
    """Схема ответа для одного appointment."""
    appointment_id: uuid.UUID
    user_id: uuid.UUID
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
    """Сообщение, отправляемое в Kafka при запросе записи."""
    appointment_id: uuid.UUID
    user_id: uuid.UUID
    patient_identifier: str
    requested_datetime: str # ISO формат
    doctor_specialty: str
    reason: Optional[str] = None
    timestamp: str # ISO формат времени отправки
    correlation_id: str # Добавляем поле

class KafkaAppointmentResult(BaseModel):
    """Сообщение с результатом обработки записи (отправляемое в Kafka)."""
    appointment_id: uuid.UUID
    user_id: uuid.UUID
    status: AppointmentStatus
    confirmed_datetime: str | None = None # ISO формат
    confirmation_details: str | None = None
    rejection_reason: str | None = None
    timestamp: str # ISO формат времени отправки
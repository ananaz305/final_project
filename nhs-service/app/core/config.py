import os
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "NHS Service"
    API_V1_STR: str = "/api/v1"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    KAFKA_CLIENT_ID: str = os.getenv("KAFKA_CLIENT_ID", "nhs-service")
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_VERIFICATION_REQUEST_TOPIC: str = "identity.verification.request"
    KAFKA_VERIFICATION_RESULT_TOPIC: str = "identity.verification.result"
    KAFKA_APPOINTMENT_REQUEST_TOPIC: str = "nhs.appointment.request"
    KAFKA_APPOINTMENT_RESULT_TOPIC: str = "nhs.appointment.result"
    KAFKA_PATIENT_DATA_REQUEST_TOPIC: str = "nhs.patient.data.request"
    KAFKA_PATIENT_DATA_RESULT_TOPIC: str = "nhs.patient.data.result"
    KAFKA_VERIFICATION_GROUP_ID: str = "nhs-verification-group"
    # KAFKA_APPOINTMENT_GROUP_ID: str = "nhs-appointment-group"

    # JWT Settings (только для проверки входящих токенов, если нужно)
    # В этом сервисе сам токен не генерируется
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-dev") # Должен совпадать с reg-login!
    ALGORITHM: str = "HS256"

    # CORS (если будут прямые запросы к сервису, хотя обычно через Gateway)
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = os.getenv("BACKEND_CORS_ORIGINS", "*")

    NHS_NUMBER_HEADER: str = "X-NHS-Number"

    class Config:
        case_sensitive = True

settings = Settings()
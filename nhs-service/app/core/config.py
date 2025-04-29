import os
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "NHS Service"
    API_V1_STR: str = "/api/v1"

    # Kafka
    KAFKA_BROKER_URL: str = os.getenv("KAFKA_BROKER", "localhost:9092")
    KAFKA_CLIENT_ID: str = "nns-service"
    IDENTITY_VERIFICATION_REQUEST_TOPIC: str = "identity.verification.request"
    IDENTITY_VERIFICATION_RESULT_TOPIC: str = "identity.verification.result"
    # Топики для "Записи к врачу"
    MEDICAL_APPOINTMENT_REQUEST_TOPIC: str = "medical.appointment.request"
    MEDICAL_APPOINTMENT_RESULT_TOPIC: str = "medical.appointment.result"

    KAFKA_VERIFICATION_GROUP_ID: str = "nns-verification-group"
    # KAFKA_APPOINTMENT_GROUP_ID: str = "nns-appointment-group"

    # JWT Settings (только для проверки входящих токенов, если нужно)
    # В этом сервисе сам токен не генерируется
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-dev") # Должен совпадать с reg-login!
    ALGORITHM: str = "HS256"

    # CORS (если будут прямые запросы к сервису, хотя обычно через Gateway)
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = os.getenv("BACKEND_CORS_ORIGINS", "*")

    class Config:
        case_sensitive = True

settings = Settings()
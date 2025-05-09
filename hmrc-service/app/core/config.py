import os
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "HMRC Service"
    API_V1_STR: str = "/api/v1"

    # Kafka
    KAFKA_BROKER_URL: str = os.getenv("KAFKA_BROKER", "localhost:9092")
    KAFKA_CLIENT_ID: str = "hmrc-service"
    IDENTITY_VERIFICATION_REQUEST_TOPIC: str = "identity.verification.request"
    IDENTITY_VERIFICATION_RESULT_TOPIC: str = "identity.verification.result"
    HMRC_DEATH_NOTIFICATION_TOPIC: str = "hmrc.death.notification"

    KAFKA_VERIFICATION_GROUP_ID: str = "hmrc-verification-group"
    # KAFKA_DEATH_EVENT_INPUT_GROUP_ID: str = "hmrc-death-event-input-group" # Если будет слушать внешние события

    # JWT Settings (только для проверки входящих токенов, если нужно)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-dev") # Должен совпадать!
    ALGORITHM: str = "HS256"

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = os.getenv("BACKEND_CORS_ORIGINS", "*")

    # Settings for death notification simulation
    SIMULATE_DEATH_EVENT: bool = True
    SIMULATE_DEATH_DELAY_SECONDS: int = 30
    SIMULATE_DEATH_NIN: str = "AB123456C" # Example NIN for simulation

    class Config:
        case_sensitive = True

settings = Settings()
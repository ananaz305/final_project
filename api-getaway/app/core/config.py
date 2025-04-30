import os
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "API Gateway"
    API_V1_STR: str = "/api"

    # Downstream service URLs
    REG_LOGIN_SERVICE_URL: str = os.getenv("REG_LOGIN_SERVICE_URL", "http://localhost:8001") # Порт по умолчанию для FastAPI
    NNS_SERVICE_URL: str = os.getenv("NNS_SERVICE_URL", "http://localhost:8002")
    HMRC_SERVICE_URL: str = os.getenv("HMRC_SERVICE_URL", "http://localhost:8003")

    # Kafka
    KAFKA_BROKER_URL: str = os.getenv("KAFKA_BROKER", "localhost:9092")
    KAFKA_CLIENT_ID: str = "api-gateway"
    ACTIVITY_LOG_TOPIC: str = "system.logs.activity"
    ACCESS_LOG_TOPIC: str = "system.logs.access"

    # JWT Settings (для проверки токенов)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-dev") # Должен совпадать!
    ALGORITHM: str = "HS256"
    # В будущем здесь будут настройки Keycloak (realm, client_id и т.д.)

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = os.getenv("BACKEND_CORS_ORIGINS", "*")

    # Таймауты для запросов к downstream сервисам (в секундах)
    SERVICE_TIMEOUT: float = 15.0

    class Config:
        case_sensitive = True

settings = Settings()
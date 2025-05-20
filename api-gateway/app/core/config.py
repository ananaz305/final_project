import os
from pydantic_settings import BaseSettings
from typing import List, Union, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "API Gateway"
    API_V1_STR: str = "/api/v1"
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = "*" # Может быть строкой "*" или списком источников

    # JWT Settings
    SECRET_KEY: str = "a_very_secret_key_for_jwt_in_gateway" # Используйте более надежный ключ и переменные окружения
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Service URLs (Используйте переменные окружения для реальных deployment'ов)
    AUTH_SERVICE_URL: str = "http://reg-login-service:8002"
    NHS_SERVICE_URL: str = "http://nhs-service:8001"
    HMRC_SERVICE_URL: str = "http://hmrc-service:8003"
    PDP_SERVICE_URL: str = "http://pdp-service:8004"

    # Kafka Settings
    KAFKA_BROKER_URL: str = "kafka:9092"
    KAFKA_LOG_TOPIC_ACTIVITY: str = "system.logs.activity"
    KAFKA_LOG_TOPIC_ACCESS: str = "system.logs.access"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = os.getenv("BACKEND_CORS_ORIGINS", "*")

    # Таймауты для запросов к downstream сервисам (в секундах)
    SERVICE_TIMEOUT: float = 15.0

    class Config:
        case_sensitive = True
        # Для загрузки из .env файла, если он есть
        # env_file = ".env"
        # env_file_encoding = 'utf-8'

settings = Settings()
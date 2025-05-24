import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "HMRC Service"
    API_V1_STR: str = "/api/v1"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    KAFKA_CLIENT_ID: str = "hmrc-service"
    IDENTITY_VERIFICATION_REQUEST_TOPIC: str = "identity.verification.request"
    IDENTITY_VERIFICATION_RESULT_TOPIC: str = "identity.verification.result"
    HMRC_DEATH_NOTIFICATION_TOPIC: str = os.getenv("HMRC_DEATH_NOTIFICATION_TOPIC", "hmrc.death.notification")

    KAFKA_VERIFICATION_GROUP_ID: str = "hmrc-verification-group"
    # KAFKA_DEATH_EVENT_INPUT_GROUP_ID: str = "hmrc-death-event-input-group" # Если будет слушать внешние события

    # JWT Settings (только для проверки входящих токенов, если нужно)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-dev") # Должен совпадать!
    ALGORITHM: str = "HS256"

    # CORS
    BACKEND_CORS_ORIGINS: str | List[str] = os.getenv("BACKEND_CORS_ORIGINS_HMRC", "*")

    # Settings for death notification simulation
    SIMULATE_DEATH_EVENT: bool = True
    SIMULATE_DEATH_DELAY_SECONDS: int = 30
    SIMULATE_DEATH_NIN: str = "AB123456C" # Example NIN for simulation

    # Опционально: Настройки базы данных, если HMRC сервис использует свою БД
    DB_USER_HMRC: Optional[str] = os.getenv("DB_USER_HMRC")
    DB_PASSWORD_HMRC: Optional[str] = os.getenv("DB_PASSWORD_HMRC")
    DB_HOST_HMRC: Optional[str] = os.getenv("DB_HOST_HMRC")
    DB_PORT_HMRC: Optional[str] = os.getenv("DB_PORT_HMRC")
    DB_NAME_HMRC: Optional[str] = os.getenv("DB_NAME_HMRC")
    DATABASE_URL_HMRC: Optional[str] = None

    # Пример группы консьюмера для HMRC сервиса
    KAFKA_HMRC_DEATH_EVENT_GROUP_ID: str = os.getenv("KAFKA_HMRC_DEATH_EVENT_GROUP_ID", "hmrc-death-event-group")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    def __init__(self, **values):
        super().__init__(**values)
        if self.DB_USER_HMRC and self.DB_PASSWORD_HMRC and self.DB_HOST_HMRC and self.DB_PORT_HMRC and self.DB_NAME_HMRC:
            self.DATABASE_URL_HMRC = (
                f"postgresql+asyncpg://{self.DB_USER_HMRC}:{self.DB_PASSWORD_HMRC}@"
                f"{self.DB_HOST_HMRC}:{self.DB_PORT_HMRC}/{self.DB_NAME_HMRC}"
            )

settings = Settings()
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from fastapi.security import OAuth2PasswordBearer

class Settings(BaseSettings):
    PROJECT_NAME: str = "NHS Service"
    API_V1_STR: str = "/api/v1"

    OAUTH2_SCHEME: OAuth2PasswordBearer = OAuth2PasswordBearer(tokenUrl="token")

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    KAFKA_CLIENT_ID: str = "nhs-service"
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
    BACKEND_CORS_ORIGINS: str | List[str] = os.getenv("BACKEND_CORS_ORIGINS_NHS", "*")

    NHS_NUMBER_HEADER: str = "X-NHS-Number"

    # Опционально: Настройки базы данных, если NHS сервис использует свою БД
    DB_USER_NHS: Optional[str] = os.getenv("DB_USER_NHS")
    DB_PASSWORD_NHS: Optional[str] = os.getenv("DB_PASSWORD_NHS")
    DB_HOST_NHS: Optional[str] = os.getenv("DB_HOST_NHS")
    DB_PORT_NHS: Optional[str] = os.getenv("DB_PORT_NHS")
    DB_NAME_NHS: Optional[str] = os.getenv("DB_NAME_NHS")
    DATABASE_URL_NHS: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    def __init__(self, **values):
        super().__init__(**values)
        if self.DB_USER_NHS and self.DB_PASSWORD_NHS and self.DB_HOST_NHS and self.DB_PORT_NHS and self.DB_NAME_NHS:
            self.DATABASE_URL_NHS = (
                f"postgresql+asyncpg://{self.DB_USER_NHS}:{self.DB_PASSWORD_NHS}@"
                f"{self.DB_HOST_NHS}:{self.DB_PORT_NHS}/{self.DB_NAME_NHS}"
            )

settings = Settings()
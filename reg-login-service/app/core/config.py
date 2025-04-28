import os
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "Registration/Login Service"
    API_V1_STR: str = "/api/v1"

    # Database
    # Construct DATABASE_URL from components or use environment variable directly
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "reg_login_db")
    DATABASE_URL: str = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    # Kafka
    KAFKA_BROKER_URL: str = os.getenv("KAFKA_BROKER", "localhost:9092")
    KAFKA_CLIENT_ID: str = "reg-login-service"
    IDENTITY_VERIFICATION_REQUEST_TOPIC: str = "identity.verification.request"
    IDENTITY_VERIFICATION_RESULT_TOPIC: str = "identity.verification.result"
    HMRC_DEATH_NOTIFICATION_TOPIC: str = "hmrc.death.notification"
    KAFKA_VERIFICATION_GROUP_ID: str = "reg-login-verification-group"
    KAFKA_DEATH_EVENT_GROUP_ID: str = "reg-login-death-event-group"

    # JWT Settings (placeholder, replace with Keycloak later)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-for-dev") # CHANGE THIS!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 # 1 hour

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = os.getenv("BACKEND_CORS_ORIGINS", "*") # Allow all for dev

    class Config:
        case_sensitive = True
        # Optional: .env file support
        # env_file = ".env"

settings = Settings() 
import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Registration/Login Service"
    API_V1_STR: str = "/api/v1"

    # Database
    # Construct DATABASE_URL from components or use environment variable directly
    DB_USER: str = os.getenv("DB_USER", "ananaz")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "ananaz")
    DB_HOST: str = os.getenv("DB_HOST", "postgres_db")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "microservice_db")
    DATABASE_URL: str = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@postgres_db:{DB_PORT}/{DB_NAME}"
    SYNC_DATABASE_URL: str = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@postgres_db:{DB_PORT}/{DB_NAME}"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
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
    BACKEND_CORS_ORIGINS: str | List[str] = os.getenv("BACKEND_CORS_ORIGINS", "*") # Allow all for dev

    class Config:
        case_sensitive = True
        # Optional: .env.txt file support
        # env_file = ".env.txt"

settings = Settings()
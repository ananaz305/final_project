import uuid
import enum
from sqlalchemy import Column, String, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates

from app.db.database import Base # Импортируем Base из database.py

class IdentifierType(str, enum.Enum):
    NIN = "NIN"
    NHS = "NHS"

class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    BLOCKED = "blocked"
    REGISTERED = "registered" # Добавляем статус REGISTERED для совместимости с JWT

class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=True)  # Пароль может отсутствовать для SSO
    status = Column(Enum(UserStatus, name="user_status_enum", create_type=True),
                    nullable=False,
                    default=UserStatus.REGISTERED, # Новый дефолт
                    index=True)
    phoneNumber = Column(String, nullable=True, index=True)

    # Поля для NIN/NHS верификации, могут быть null при Google SSO регистрации
    identifierType = Column(Enum(IdentifierType, name="identifier_type_enum", create_type=True),
                            nullable=True, # Сделаем nullable
                            index=True)
    identifierValue = Column(String, nullable=True, index=True) # Сделаем nullable

    auth_provider = Column(Enum(AuthProvider, name="auth_provider_enum", create_type=True),
                           nullable=False,
                           default=AuthProvider.EMAIL, # По умолчанию 'email'
                           index=True)

    # Убираем UniqueConstraint для identifierType, identifierValue, так как они теперь nullable
    # Если они должны быть уникальны КОГДА НЕ NULL, это потребует более сложного constraint или логики в приложении
    # Пока что, для простоты, предполагаем, что уникальность email достаточна для Google SSO
    # __table_args__ = (UniqueConstraint('identifierType', 'identifierValue', name='uq_user_identifier'),)
    # Если identifierType и identifierValue ДОЛЖНЫ быть уникальной парой, когда они оба ЗАПОЛНЕНЫ,
    # то это потребует создания partial index в PostgreSQL или проверки на уровне приложения.
    # Для текущей задачи (Google SSO), где эти поля могут быть изначально пустыми, убираем constraint.

    # Пример валидации (необязательно, Pydantic обычно используется для входных данных)
    @validates('email')
    def validate_email(self, key, email):
        if '@' not in email:
            raise ValueError("Неверный формат email")
        return email

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', status='{self.status}')>"
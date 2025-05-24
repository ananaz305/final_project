import uuid
# import enum # Больше не нужен здесь напрямую
from sqlalchemy import Column, String, Enum as SQLAlchemyEnum, UniqueConstraint # Переименовываем Enum, чтобы избежать конфликта
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import ENUM

from app.db.database import Base
# Импортируем Enum из общего модуля
from shared.kafka_client_lib.enums import IdentifierType, UserStatus, AuthProvider

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=True)  # Пароль может отсутствовать для SSO
    status = Column(SQLAlchemyEnum(UserStatus, name="user_status_enum", create_type=False),
                    nullable=False,
                    default=UserStatus.REGISTERED, # Новый дефолт
                    index=True)
    phoneNumber = Column(String, nullable=True, index=True)

    # Поля для NIN/NHS верификации, могут быть null при Google SSO регистрации
    identifierType = Column(SQLAlchemyEnum(IdentifierType, name="identifier_type_enum", create_type=False),
                            nullable=True, # Сделаем nullable
                            index=True)
    identifierValue = Column(String, nullable=True, index=True) # Сделаем nullable

    auth_provider = Column(SQLAlchemyEnum(AuthProvider, name="auth_provider_enum", create_type=False),
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
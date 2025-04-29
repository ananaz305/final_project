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

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifierType = Column(Enum(IdentifierType, name="identifier_type_enum", create_type=True),
                            nullable=False,
                            index=True)
    identifierValue = Column(String, nullable=False, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False) # Хранится хэш
    status = Column(Enum(UserStatus, name="user_status_enum", create_type=True),
                    nullable=False,
                    default=UserStatus.PENDING_VERIFICATION,
                    index=True)
    phoneNumber = Column(String, nullable=True)

    # Добавляем составной уникальный индекс
    __table_args__ = (UniqueConstraint('identifierType', 'identifierValue', name='uq_user_identifier'),)

    # Пример валидации (необязательно, Pydantic обычно используется для входных данных)
    @validates('email')
    def validate_email(self, key, email):
        if '@' not in email:
            raise ValueError("Неверный формат email")
        return email

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', status='{self.status}')>"
import uuid
# import enum # No longer needed here directly
from sqlalchemy import Column, String, Enum as SQLAlchemyEnum, UniqueConstraint  # Renaming Enum to avoid conflict
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import ENUM

from app.db.database import Base
# Import Enum from shared module
from shared.kafka_client_lib.enums import IdentifierType, UserStatus, AuthProvider

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=True)  # Password may be missing for SSO
    status = Column(SQLAlchemyEnum(UserStatus, name="user_status_enum", create_type=False),
                    nullable=False,
                    default=UserStatus.REGISTERED,  # New default
                    index=True)
    phoneNumber = Column(String, nullable=True, index=True)

    # Fields for NIN/NHS verification, may be null during Google SSO registration
    identifierType = Column(SQLAlchemyEnum(IdentifierType, name="identifier_type_enum", create_type=False),
                            nullable=True,  # Make nullable
                            index=True)
    identifierValue = Column(String, nullable=True, index=True)  # Make nullable

    auth_provider = Column(SQLAlchemyEnum(AuthProvider, name="auth_provider_enum", create_type=False),
                           nullable=False,
                           default=AuthProvider.EMAIL,  # Default to 'email'
                           index=True)

    # Removing UniqueConstraint for identifierType and identifierValue, since they are now nullable
    # If they must be unique WHEN NOT NULL, it would require a more complex constraint or application-level logic
    # For simplicity, assume email uniqueness is sufficient for Google SSO
    # __table_args__ = (UniqueConstraint('identifierType', 'identifierValue', name='uq_user_identifier'),)
    # If identifierType and identifierValue MUST be a unique pair WHEN BOTH ARE PRESENT,
    # this requires creating a partial index in PostgreSQL or a check in application code.
    # For the current case (Google SSO), where these fields can initially be empty, we remove the constraint.

    # Example validation (optional, usually done via Pydantic for input)
    @validates('email')
    def validate_email(self, key, email):
        if '@' not in email:
            raise ValueError("Invalid email format")
        return email

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', status='{self.status}')>"

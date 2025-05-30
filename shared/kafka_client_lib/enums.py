import enum

class IdentifierType(str, enum.Enum):
    NIN = "NIN"
    NHS = "NHS"

class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    BLOCKED = "blocked"
    REGISTERED = "registered"

class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    # GOOGLE = "google"
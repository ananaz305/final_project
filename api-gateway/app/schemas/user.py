import enum
from pydantic import BaseModel

# The definition of UserStatus should be here, as it is used in TokenPayload
# This definition is taken from reg-login-service/app/models/user.py
class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    BLOCKED = "blocked"
    REGISTERED = "registered"

class TokenPayload(BaseModel):
    sub: str # This is usually the user ID (UUID in our case)
    status: UserStatus # The status is required in our JWT
    # Additional fields, if they are in the token and needed by the gateway (for example, email, roles),
    # can be added here, but they must also be in TokenPayload in reg-login-service
    # and added when creating the token.
    # A sub and a status are enough for an MVP.


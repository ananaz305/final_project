import enum
from pydantic import BaseModel

# Определение UserStatus должно быть здесь, так как оно используется в TokenPayload
# Это определение взято из reg-login-service/app/models/user.py
class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    BLOCKED = "blocked"
    REGISTERED = "registered"

class TokenPayload(BaseModel):
    sub: str # Обычно это user ID (UUID в нашем случае)
    status: UserStatus # Статус обязателен в нашем JWT
    # Дополнительные поля, если они есть в токене и нужны шлюзу (например, email, roles),
    # можно добавить сюда, но они также должны быть в TokenPayload в reg-login-service
    # и добавляться при создании токена.
    # Для MVP достаточно sub и status.
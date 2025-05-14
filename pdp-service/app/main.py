import json
import logging
import os
from pathlib import Path
from typing import List, Any, Literal, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

# --- Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
POLICIES_DIR = Path(os.getenv("POLICIES_DIR", "./policies"))

# --- Logging Setup ---
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("pdp-service")

# --- Pydantic Models ---

class UserContext(BaseModel):
    status: Optional[str] = None
    role: Optional[str] = None
    # Add other relevant user attributes here as needed

class RequestContext(BaseModel):
    service: Optional[str] = None
    action: Optional[str] = None
    # Add other relevant request/resource attributes here

class AuthorizationRequest(BaseModel):
    user: UserContext = Field(default_factory=UserContext)
    request: RequestContext = Field(default_factory=RequestContext)
    # We can add 'resource' or 'environment' contexts later if needed

class AuthorizationResponse(BaseModel):
    decision: Literal["allow", "deny"]

class PolicyCondition(BaseModel):
    attribute: str # e.g., "user.status", "request.service"
    operator: Literal["equals", "not_equals", "in", "not_in"] # Supported operators
    value: Any # The value to compare against

class Policy(BaseModel):
    id: str # Unique policy identifier (e.g., filename without extension)
    description: str
    effect: Literal["allow", "deny"]
    conditions: List[PolicyCondition] = Field(default_factory=list) # All conditions must match (AND logic)

# --- Policy Loading ---

def load_policies(policies_dir: Path) -> List[Policy]:
    """Loads all policies from JSON files in the specified directory."""
    loaded_policies: List[Policy] = []
    if not policies_dir.is_dir():
        logger.error(f"Policies directory not found: {policies_dir}")
        return loaded_policies

    for policy_file in policies_dir.glob("*.json"):
        try:
            with open(policy_file, 'r') as f:
                policy_data = json.load(f)
                # Add the filename (without extension) as the policy ID if not present
                if "id" not in policy_data:
                    policy_data["id"] = policy_file.stem
                policy = Policy(**policy_data)
                loaded_policies.append(policy)
                logger.info(f"Loaded policy '{policy.id}' from {policy_file.name}")
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from policy file: {policy_file.name}")
        except Exception as e:
            logger.error(f"Error loading policy from {policy_file.name}: {e}")
    return loaded_policies

# --- Policy Evaluation Logic ---

def get_attribute_value(context: BaseModel, attribute_path: str) -> Any:
    """Safely gets a nested attribute value from a context object."""
    parts = attribute_path.split('.')
    value = context
    try:
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else: # It's a Pydantic model
                value = getattr(value, part, None)
            if value is None:
                return None # Attribute not found
    except AttributeError:
        return None
    return value

def evaluate_condition(condition: PolicyCondition, request_data: AuthorizationRequest) -> bool:
    """Evaluates a single policy condition against the request context."""
    attribute_path = condition.attribute
    context_name = attribute_path.split('.')[0] # e.g., 'user', 'request'

    if context_name == 'user':
        context_obj = request_data.user
    elif context_name == 'request':
        context_obj = request_data.request
    else:
        logger.warning(f"Unknown context '{context_name}' in condition attribute '{attribute_path}'")
        return False # Or handle differently based on requirements

    actual_value = get_attribute_value(context_obj, attribute_path.split('.', 1)[1] if '.' in attribute_path else '' )
    expected_value = condition.value

    if condition.operator == "equals":
        return actual_value == expected_value
    elif condition.operator == "not_equals":
        return actual_value != expected_value
    elif condition.operator == "in":
        return isinstance(expected_value, list) and actual_value in expected_value
    elif condition.operator == "not_in":
        return isinstance(expected_value, list) and actual_value not in expected_value
    else:
        logger.warning(f"Unsupported operator '{condition.operator}' in policy condition.")
        return False

def evaluate_policies(current_policies: List[Policy], request_data: AuthorizationRequest) -> Literal["allow", "deny"]:
    """
    Evaluates the request against current policies.
    Uses a deny-overrides approach: if any deny policy matches, the result is deny.
    If one or more allow policies match and no deny policies match, the result is allow.
    Otherwise (no matching policies), the result is deny.
    """
    matching_allows = False

    # Deny overrides
    for policy in current_policies:
        if policy.effect == "deny":
            conditions_met = all(evaluate_condition(cond, request_data) for cond in policy.conditions)
            if conditions_met:
                logger.info(f"Deny decision based on policy: {policy.id}. User: {request_data.user.model_dump(exclude_none=True)}, Request: {request_data.request.model_dump(exclude_none=True)}")
                return "deny"

    # Check allows if no deny matched
    for policy in current_policies:
        if policy.effect == "allow":
            conditions_met = all(evaluate_condition(cond, request_data) for cond in policy.conditions)
            if conditions_met:
                logger.info(f"Allow condition met by policy: {policy.id}")
                matching_allows = True
                # Don't return immediately, check all denies first

    if matching_allows:
        logger.info("Final decision: allow. User: {request_data.user.model_dump(exclude_none=True)}, Request: {request_data.request.model_dump(exclude_none=True)}")
        return "allow"
    else:
        logger.info("Final decision: deny (no matching allow, or explicit deny). User: {request_data.user.model_dump(exclude_none=True)}, Request: {request_data.request.model_dump(exclude_none=True)}")
        return "deny" # Default deny

# --- FastAPI App ---

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Загружает политики при старте приложения."""
    global policies_store
    logger.info(f"PDP Service starting up. Loading policies from: {POLICIES_DIR.resolve()}")
    policies_store = load_policies(POLICIES_DIR)
    logger.info(f"Loaded {len(policies_store)} policies.")
    yield
    logger.info("PDP Service shutting down.")
    # Здесь можно добавить логику очистки, если необходимо

app = FastAPI(
    title="Simple Policy Decision Point (PDP) Service",
    description="Evaluates authorization requests based on local JSON policies.",
    version="0.1.0",
    lifespan=lifespan # Используем lifespan
)

# @app.on_event("startup") # Удалено
# async def startup_event():
# global policies
# logger.info(f"Loading policies from: {POLICIES_DIR.resolve()}")
# policies = load_policies(POLICIES_DIR)
# logger.info(f"Loaded {len(policies)} policies.")

@app.post("/authorize", response_model=AuthorizationResponse)
async def authorize_endpoint(request_data: AuthorizationRequest, request: Request): # Переименовано authorize_request в authorize_endpoint
    """
    Evaluates an authorization request based on loaded policies.
    Receives user context and request context, returns allow/deny decision.
    """
    client_host = request.client.host if request.client else "unknown"
    # Улучшенное логирование с исключением None значений для краткости
    logger.info(f"Received authorization request from {client_host}: User={request_data.user.model_dump(exclude_none=True)}, Request={request_data.request.model_dump(exclude_none=True)}")

    if not policies_store:
        logger.warning("No policies loaded. Defaulting to deny. This may indicate an issue with policy loading.")
        # В этом случае стоит вернуть ошибку сервера, т.к. система не сконфигурирована
        # raise HTTPException(status_code=503, detail="Service Unavailable: No policies loaded")
        # Однако, для простоты mock, оставляем deny
        return AuthorizationResponse(decision="deny")

    decision = evaluate_policies(policies_store, request_data)
    logger.info(f"Authorization decision for request from {client_host}: {decision}")
    return AuthorizationResponse(decision=decision)

@app.get("/health")
async def health_check_endpoint(): # Переименовано health_check в health_check_endpoint
    """Предоставляет информацию о состоянии сервиса и количестве загруженных политик."""
    return {"status": "ok", "loaded_policies_count": len(policies_store), "policies_directory": str(POLICIES_DIR.resolve())}

# --- Run with Uvicorn (для локального тестирования закомментировано) ---
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001, log_level=LOG_LEVEL.lower())

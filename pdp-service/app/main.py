import json
import logging
import os
from pathlib import Path
from typing import List, Any, Literal
from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request, HTTPException, status
from pydantic import BaseModel, Field

# --- Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
POLICIES_DIR = Path(os.getenv("POLICIES_DIR", "./policies"))

# --- Logging Setup ---
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("pdp-service")

# --- In-memory Policy Store (for demonstration) ---
# In a real application, policies would come from a database or a config file.
policies_store: List["Policy"] = []

# --- Pydantic Models ---

class UserContext(BaseModel):
    id: str | None = None
    roles: List[str] = Field(default_factory=list)
    status: str | None = None
    # Add other relevant user attributes here

class RequestContext(BaseModel):
    service: str | None = None
    action: str | None = None
    # Add other relevant request/resource attributes here

class AuthorizationRequest(BaseModel):
    user: UserContext
    request: RequestContext
    # You can add more context like environment, resource attributes, etc.

class AuthorizationResponse(BaseModel):
    decision: Literal["allow", "deny"]

class PolicyCondition(BaseModel):
    attribute: str # e.g., "user.status", "request.service"
    operator: Literal["equals", "not_equals", "in", "not_in"] # Supported operators
    value: Any # The value to compare against

class Policy(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())) # Unique policy identifier
    description: str
    effect: Literal["allow", "deny"]
    conditions: List[PolicyCondition] = Field(default_factory=list) # All conditions must match (AND logic)
    priority: int = 0 # Higher numbers mean higher priority

class PolicyResponse(Policy):
    pass

class Decision(BaseModel):
    allowed: bool
    reason: str | None = None
    matched_policy_id: str | None = None

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

def get_attribute_value(obj: BaseModel | None, attribute_path: str) -> Any | None:
    """Retrieves a nested attribute value from a Pydantic model using a dot-separated path."""
    if obj is None:
        return None
    current_value = obj
    for part in attribute_path.split('.'):
        if isinstance(current_value, BaseModel):
            if hasattr(current_value, part):
                current_value = getattr(current_value, part)
            else:
                # logger.debug(f"Attribute '{part}' not found in {type(current_value)}")
                return None # Attribute not found
        elif isinstance(current_value, dict):
            current_value = current_value.get(part)
            if current_value is None:
                # logger.debug(f"Key '{part}' not found in dict")
                return None # Key not found
        else:
            # logger.debug(f"Cannot get attribute '{part}' from non-model/dict type {type(current_value)}")
            return None # Path leads to a non-dictionary/model type
    return current_value

def evaluate_condition(condition: PolicyCondition, request_data: AuthorizationRequest) -> bool:
    """Evaluates a single policy condition against the request context."""
    attribute_path = condition.attribute
    context_name = attribute_path.split('.')[0] # e.g., 'user', 'request'

    context_obj: BaseModel | None = None
    attribute_name_in_context: str

    if context_name == 'user':
        context_obj = request_data.user
        attribute_name_in_context = attribute_path.split('.', 1)[1] if '.' in attribute_path else ''
    elif context_name == 'request':
        context_obj = request_data.request
        attribute_name_in_context = attribute_path.split('.', 1)[1] if '.' in attribute_path else ''
    else:
        logger.warning(f"Unknown context '{context_name}' in condition attribute '{attribute_path}'")
        return False

    actual_value = get_attribute_value(context_obj, attribute_name_in_context)
    expected_value = condition.value

    # logger.debug(f"Evaluating condition: attr='{condition.attribute}', op='{condition.operator}', exp_val='{expected_value}', act_val='{actual_value}'")

    if condition.operator == "equals":
        return actual_value == expected_value
    elif condition.operator == "not_equals":
        return actual_value != expected_value
    elif condition.operator == "in":
        return isinstance(expected_value, list) and actual_value in expected_value
    elif condition.operator == "not_in":
        # Ensure actual_value is not None before checking if it's not in the list for "not_in"
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
async def lifespan(app: FastAPI):
    """Loads the policies when the application starts."""
    global policies_store
    logger.info(f"PDP Service starting up. Loading policies from: {POLICIES_DIR.resolve()}")
    policies_store = load_policies(POLICIES_DIR)
    logger.info(f"Loaded {len(policies_store)} policies.")
    yield
    logger.info("PDP Service shutting down.")
    # Here you can add the cleaning logic, if necessary.

app = FastAPI(
    title="Simple Policy Decision Point (PDP) Service",
    description="Evaluates authorization requests based on local JSON policies.",
    version="0.1.0",
    lifespan=lifespan # Using lifespan
)

# @app.on_event("startup") # Удалено
# async def startup_event():
# global policies
# logger.info(f"Loading policies from: {POLICIES_DIR.resolve()}")
# policies = load_policies(POLICIES_DIR)
# logger.info(f"Loaded {len(policies)} policies.")

@app.post("/decide", response_model=Decision)
async def decide_authorization(auth_request: AuthorizationRequest) -> Decision:
    """Evaluates policies against the given request and returns an authorization decision."""
    logger.info(f"Decision request for user: {auth_request.user.id}, service: {auth_request.request.service}, action: {auth_request.request.action}")

    # Sort policies by priority (descending, higher first)
    sorted_policies = sorted(policies_store, key=lambda p: p.priority, reverse=True)

    # First-applicable strategy: evaluate policies in order of priority
    # The first policy that results in a DENY immediately returns DENY.
    # If a DENY is found, we stop. If an ALLOW is found, we record it and continue (unless it's the highest priority allow).
    # For simplicity in this example: first matching explicit DENY wins, then first matching explicit ALLOW wins.
    # A default deny is usually at the end with lowest priority.

    matched_allow_policy: Policy | None = None

    for policy in sorted_policies:
        all_conditions_met = True
        if not policy.conditions: # If a policy has no conditions, it's always applicable
            pass # Conditions met by default (or lack thereof)
        else:
            for condition in policy.conditions:
                if not evaluate_condition(condition, auth_request):
                    all_conditions_met = False
                    break # Move to the next policy if any condition is not met

        if all_conditions_met:
            logger.info(f"Policy '{policy.id}' ({policy.effect}) matched with priority {policy.priority}.")
            if policy.effect == "deny":
                logger.info(f"Decision: DENY based on policy '{policy.id}'")
                return Decision(allowed=False, reason=f"Denied by policy: {policy.description}", matched_policy_id=policy.id)
            elif policy.effect == "allow":
                # If we find an allow, we can consider it, but a higher priority deny might still exist or come later if priorities are not strict.
                # For this example, the first allow we hit (after checking denies up to this point based on sort order) will grant access.
                logger.info(f"Decision: ALLOW based on policy '{policy.id}'")
                return Decision(allowed=True, reason=f"Allowed by policy: {policy.description}", matched_policy_id=policy.id)

    # This part is reached if no explicit allow or deny was hit from policies with conditions.
    # This usually means only a default policy (like default_deny_all) would apply.
    # However, the loop above should handle the default_deny_all if it's present and has no conditions.

    logger.warning(f"No specific policy matched or resulted in a decision for request. This might imply a configuration issue or rely on an implicit default.")
    # Fallback to a default deny if no policy explicitly allowed. This is safer.
    # This should ideally be covered by a low-priority "default_deny_all" policy.
    return Decision(allowed=False, reason="No policy explicitly allowed the request, and no explicit deny was hit before. Defaulting to deny.", matched_policy_id=None)

@app.get("/policies", response_model=List[PolicyResponse])
async def list_policies():
    """Lists all currently loaded policies."""
    return policies_store

@app.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(policy_data: Policy):
    """Creates a new policy."""
    # Basic validation: check if ID already exists (though UUIDs should be unique)
    if any(p.id == policy_data.id for p in policies_store):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Policy with ID '{policy_data.id}' already exists.")
    policies_store.append(policy_data)
    logger.info(f"Policy '{policy_data.id}' created.")
    return policy_data

@app.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(policy_id: str):
    """Retrieves a specific policy by its ID."""
    policy = next((p for p in policies_store if p.id == policy_id), None)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy with ID '{policy_id}' not found.")
    return policy

@app.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(policy_id: str, policy_data: Policy):
    """Updates an existing policy."""
    policy_index = next((i for i, p in enumerate(policies_store) if p.id == policy_id), -1)
    if policy_index == -1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy with ID '{policy_id}' not found.")
    # Ensure the ID in the path matches the ID in the body, or update it if it's part of the update
    if policy_data.id != policy_id:
        # Option 1: Reject if IDs don't match and ID is not meant to be updatable this way
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy ID in path and body do not match.")
        # Option 2: Allow ID update (be cautious with this, usually ID is immutable or changed via a different process)
        logger.warning(f"Policy ID in path '{policy_id}' and body '{policy_data.id}' differ. Using body ID for update.")
        pass # Assuming policy_data.id is the new source of truth

    policies_store[policy_index] = policy_data
    logger.info(f"Policy '{policy_id}' updated.")
    return policy_data

@app.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(policy_id: str):
    """Deletes a policy by its ID."""
    global policies_store
    initial_len = len(policies_store)
    policies_store = [p for p in policies_store if p.id != policy_id]
    if len(policies_store) == initial_len:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy with ID '{policy_id}' not found.")
    logger.info(f"Policy '{policy_id}' deleted.")
    return # Return None for 204 No Content

# Basic health check endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy"}

# --- Run with Uvicorn ---
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001, log_level=LOG_LEVEL.lower())

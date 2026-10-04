"""Sign-in endpoints for the deployment-configured operator account."""

import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.security import issue_access_token
from app.security import require_request_identity

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(payload: LoginRequest) -> dict:
    settings = get_settings()
    if not settings.auth_admin_username or not settings.auth_admin_password:
        raise HTTPException(status_code=503, detail="Operator login is not configured on the server.")
    valid_user = hmac.compare_digest(payload.username, settings.auth_admin_username)
    valid_password = hmac.compare_digest(payload.password, settings.auth_admin_password)
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="Username or password is incorrect.")
    token, expires_in = issue_access_token(payload.username)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


@router.get("/me")
def current_user(request: Request) -> dict:
    # The API middleware has already validated this bearer token.
    return {"username": require_request_identity(request)}

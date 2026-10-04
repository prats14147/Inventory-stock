"""Small, dependency-free HS256 token helpers for the configured operator."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException, Request, WebSocket, status

from app.config import get_settings


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def issue_access_token(username: str) -> tuple[str, int]:
    settings = get_settings()
    if not settings.auth_admin_username or not settings.auth_admin_password:
        raise HTTPException(status_code=503, detail="Operator login is not configured on the server.")
    if len(settings.auth_token_secret) < 32:
        raise HTTPException(status_code=503, detail="AUTH_TOKEN_SECRET must contain at least 32 characters.")
    ttl = max(5, settings.auth_token_ttl_minutes) * 60
    now = int(time.time())
    header = _encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _encode(json.dumps({"sub": username, "iat": now, "exp": now + ttl}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(settings.auth_token_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_encode(signature)}", ttl


def get_token_identity(token: str | None) -> str | None:
    settings = get_settings()
    if not token or len(settings.auth_token_secret) < 32:
        return None
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}".encode("ascii")
        expected = _encode(hmac.new(settings.auth_token_secret.encode(), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        decoded_header = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if decoded_header.get("alg") != "HS256" or int(claims.get("exp", 0)) <= int(time.time()):
            return None
        username = claims.get("sub")
        return username if username == settings.auth_admin_username else None
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def require_request_identity(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    return get_token_identity(token) if scheme.lower() == "bearer" else None


def require_websocket_identity(websocket: WebSocket) -> str | None:
    authorization = websocket.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        token = next(
            (protocol.removeprefix("bearer.") for protocol in websocket.scope.get("subprotocols", []) if protocol.startswith("bearer.")),
            None,
        )
    return get_token_identity(token)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to access InventoryAI.",
        headers={"WWW-Authenticate": "Bearer"},
    )

"""Password hashing and short-lived signed session tokens."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request, WebSocket, status

from app.config import get_settings
from app.database import SessionLocal

PASSWORD_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        candidate = _encode(hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            base64.urlsafe_b64decode(salt + "=" * (-len(salt) % 4)), iterations,
        ))
        return hmac.compare_digest(candidate, expected)
    except (ValueError, TypeError):
        return False


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def issue_access_token(user) -> tuple[str, int]:
    settings = get_settings()
    if len(settings.auth_token_secret) < 32:
        raise HTTPException(status_code=503, detail="AUTH_TOKEN_SECRET must contain at least 32 characters.")
    ttl = max(5, settings.auth_token_ttl_minutes) * 60
    now = int(time.time())
    header = _encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _encode(json.dumps({
        "sub": user.username,
        "uid": user.id,
        "ver": user.session_version,
        "iat": now,
        "exp": now + ttl,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(settings.auth_token_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_encode(signature)}", ttl


def _decode_token(token: str | None) -> dict | None:
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
        if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("uid"), int):
            return None
        return claims
    except (ValueError, TypeError, KeyError, binascii.Error, json.JSONDecodeError):
        return None


def require_request_identity(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    claims = _decode_token(token)
    if claims is None:
        return None
    from app.models.user_account import UserAccount

    with SessionLocal() as db:
        user = db.get(UserAccount, claims["uid"])
        if (
            user is None
            or not user.is_active
            or user.username != claims["sub"]
            or user.session_version != claims.get("ver")
        ):
            return None
        request.state.authenticated_user = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
            "must_change_password": user.must_change_password,
        }
        return user.username


def require_websocket_identity(websocket: WebSocket) -> dict | None:
    authorization = websocket.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        token = next(
            (protocol.removeprefix("bearer.") for protocol in websocket.scope.get("subprotocols", []) if protocol.startswith("bearer.")),
            None,
        )
    claims = _decode_token(token)
    if claims is None:
        return None
    from app.models.user_account import UserAccount

    with SessionLocal() as db:
        user = db.get(UserAccount, claims["uid"])
        if (
            user is None or not user.is_active or user.username != claims["sub"]
            or user.session_version != claims.get("ver")
        ):
            return None
        return {"id": user.id, "username": user.username, "role": user.role}


def get_token_identity(token: str | None) -> str | None:
    """Compatibility helper returning the signed subject (username)."""
    claims = _decode_token(token)
    return claims.get("sub") if claims else None


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to access InventoryAI.",
        headers={"WWW-Authenticate": "Bearer"},
    )

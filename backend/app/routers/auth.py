"""Database-backed user accounts, role management, and password recovery."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user_account import PasswordResetToken, UserAccount
from app.security import hash_password, issue_access_token, require_request_identity, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
log = logging.getLogger("app.auth")
RESET_TTL_MINUTES = 30
_rate_lock = threading.Lock()
_attempts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(key: str, limit: int, window_seconds: int, *, record: bool) -> bool:
    now = time.monotonic()
    with _rate_lock:
        attempts = _attempts[key]
        while attempts and attempts[0] <= now - window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            return True
        if record:
            attempts.append(now)
        return False


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern=r"^(admin|manager|viewer)$")
    temporary_password: str = Field(min_length=12, max_length=200)


class UserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(admin|manager|viewer)$")
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class ProfileUpdateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)


def _valid_email(email: str) -> bool:
    return "@" in email and "." in email.rsplit("@", 1)[-1] and not any(ch.isspace() for ch in email)


def _public_user(user: UserAccount) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


def _current_user(request: Request, db: Session) -> UserAccount:
    identity = require_request_identity(request)
    details = getattr(request.state, "authenticated_user", None)
    user = db.get(UserAccount, details["id"]) if identity and details else None
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to access InventoryAI.")
    return user


def _send_reset_email(recipient: str, token: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        log.warning("Password reset requested but SMTP is not configured.")
        return
    url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
    message = EmailMessage()
    message["Subject"] = "Reset your InventoryAI password"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your InventoryAI account.\n\n"
        f"Use this link within {RESET_TTL_MINUTES} minutes:\n{url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ssl.create_default_context(), timeout=15) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    username = payload.username.strip()
    normalized = username.lower()
    ip = request.client.host if request.client else "unknown"
    rate_key = f"login:{ip}"
    if _rate_limited(rate_key, 10, 15 * 60, record=False):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")
    user = db.scalar(select(UserAccount).where(func.lower(UserAccount.username) == normalized))

    # The environment credentials are a one-time bootstrap mechanism only.
    # They create the initial database admin; future logins use its password hash.
    if user is None and db.scalar(select(func.count()).select_from(UserAccount)) == 0:
        settings = get_settings()
        if not settings.auth_admin_username or not settings.auth_admin_password:
            raise HTTPException(status_code=503, detail="Initial admin login is not configured. Set AUTH_ADMIN_USERNAME and AUTH_ADMIN_PASSWORD on the server.")
        valid_user = bool(settings.auth_admin_username) and hmac.compare_digest(username, settings.auth_admin_username)
        valid_password = bool(settings.auth_admin_password) and hmac.compare_digest(payload.password, settings.auth_admin_password)
        if valid_user and valid_password:
            user = UserAccount(
                username=settings.auth_admin_username.strip().lower(),
                email=settings.auth_admin_email.strip().lower() or f"{normalized}@localhost",
                display_name="Administrator",
                password_hash=hash_password(payload.password),
                role="admin",
                is_active=True,
            )
            db.add(user)
            try:
                db.commit()
                db.refresh(user)
            except IntegrityError:
                db.rollback()
                user = db.scalar(select(UserAccount).where(func.lower(UserAccount.username) == normalized))

    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        _rate_limited(rate_key, 10, 15 * 60, record=True)
        raise HTTPException(status_code=401, detail="Username or password is incorrect.")
    with _rate_lock:
        _attempts.pop(rate_key, None)
    token, expires_in = issue_access_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": _public_user(user)}


@router.get("/me")
def current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    return _public_user(_current_user(request, db))


@router.patch("/me")
def update_profile(payload: ProfileUpdateRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    if not _valid_email(payload.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if not payload.display_name.strip():
        raise HTTPException(status_code=422, detail="Display name cannot be blank.")
    user = _current_user(request, db)
    user.email = payload.email.strip().lower()
    user.display_name = payload.display_name.strip()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email address is already in use.") from exc
    db.refresh(user)
    return _public_user(user)


@router.post("/change-password")
def change_password(payload: PasswordChangeRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user(request, db)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if hmac.compare_digest(payload.current_password, payload.new_password):
        raise HTTPException(status_code=400, detail="Choose a password different from the current one.")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.session_version += 1
    db.commit()
    return {"message": "Password changed. Sign in again with the new password."}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user(request, db)
    user.session_version += 1
    db.commit()
    return {"message": "Signed out."}


@router.get("/users")
def list_users(request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _current_user(request, db)
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage user accounts.")
    users = db.scalars(select(UserAccount).order_by(UserAccount.created_at, UserAccount.id)).all()
    return {"users": [_public_user(user) for user in users]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _current_user(request, db)
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create user accounts.")
    if not _valid_email(payload.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if not payload.display_name.strip():
        raise HTTPException(status_code=422, detail="Display name cannot be blank.")
    user = UserAccount(
        username=payload.username.strip().lower(),
        email=payload.email.strip().lower(),
        display_name=payload.display_name.strip(),
        role=payload.role,
        password_hash=hash_password(payload.temporary_password),
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username or email is already registered.") from exc
    db.refresh(user)
    return _public_user(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdateRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _current_user(request, db)
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage user accounts.")
    user = db.get(UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    updates = payload.model_dump(exclude_none=True)
    if user.id == actor.id and updates.get("is_active") is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    if user.role == "admin" and (updates.get("role", "admin") != "admin" or updates.get("is_active") is False):
        active_admins = db.scalar(select(func.count()).select_from(UserAccount).where(UserAccount.role == "admin", UserAccount.is_active.is_(True))) or 0
        if user.is_active and active_admins <= 1:
            raise HTTPException(status_code=400, detail="Keep at least one active admin account.")
    for key, value in updates.items():
        setattr(user, key, value)
    if updates.get("is_active") is False or "role" in updates:
        user.session_version += 1
    db.commit()
    db.refresh(user)
    return _public_user(user)


@router.post("/password-reset/request", status_code=202)
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(f"reset:{ip}", 5, 60 * 60, record=True):
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again later.")
    # Keep the response identical whether or not the account exists.
    user = db.scalar(select(UserAccount).where(func.lower(UserAccount.email) == payload.email.strip().lower(), UserAccount.is_active.is_(True)))
    settings = get_settings()
    if user and settings.smtp_host and settings.smtp_from_email:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MINUTES)))
        db.commit()
        try:
            _send_reset_email(user.email, raw_token)
        except (OSError, smtplib.SMTPException):
            log.exception("Could not send password reset email.")
    elif user:
        log.warning("Password reset requested but SMTP is not configured; reset email was not sent.")
    return {
        "message": "If an active account matches that email, a password reset link will be sent.",
        "email_delivery_configured": bool(settings.smtp_host and settings.smtp_from_email),
    }


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)) -> dict:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    reset = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash, PasswordResetToken.used_at.is_(None))
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if reset is None or reset.expires_at <= now:
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired. Request a new one.")
    user = db.get(UserAccount, reset.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired. Request a new one.")
    reset.used_at = now
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.session_version += 1
    # Revoke any other outstanding reset links for this account.
    for other in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))):
        other.used_at = now
    db.commit()
    return {"message": "Password reset. You can now sign in with your new password."}

"""
services/security.py
────────────────────
Password hashing (bcrypt) and JWT session-token utilities for the dashboard.

Design: session-cookie auth. A login issues a signed JWT stored in an
httponly cookie. Every /api/* call is scoped to the user's merchant_id via
the `get_current_user` FastAPI dependency declared in bulk_auth.

All production-grade hygiene is respected:
  - passwords are bcrypt-hashed (never stored/returned in plaintext)
  - JWTs are signed with HMAC-SHA256 and a per-install secret
  - the cookie is httponly + samesite=lax (browser JS cannot read the token)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.connection import get_db
from app.db.models import User

logger = logging.getLogger(__name__)

SESSION_COOKIE = "autodefend_session"


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ── JWT tokens ───────────────────────────────────────────────────────────────

def create_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "merchant_id": user.merchant_id,
        "is_admin": user.is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token.")


# ── Cookie helpers ───────────────────────────────────────────────────────────

def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


# ── FastAPI dependency: authenticated user from the session cookie ───────────

def get_current_user(
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in user from the httponly session cookie.

    Used as a FastAPI security dependency on protected routes:
        def list_disputes(current: User = Depends(get_current_user), db=Depends(get_db)):
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    payload = decode_token(session_token)
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return user
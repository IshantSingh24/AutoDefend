"""
api/bulk_auth.py
────────────────
User registration, login, session resolution, and logout.

Auth model: session cookie (httponly JWT). After login the browser holds a
signed token; every protected /api/* route resolves the user via the
`get_current_user` dependency and scopes queries to that user's merchant_id.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import User
from app.services.security import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_token,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=128)
    merchant_id: str = Field(min_length=2, max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "merchant_id": user.merchant_id,
        "is_admin": user.is_admin,
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Create a merchant account. Merchant_id scopes their data (multi-tenant)."""
    exists = db.query(User).filter(User.email == body.email.lower()).first()
    if exists:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        merchant_id=body.merchant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    set_session_cookie(response, create_token(user))
    logger.info("Registered user %s (merchant %s)", user.email, user.merchant_id)
    return _public_user(user)


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Verify credentials and start a session cookie."""
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    set_session_cookie(response, create_token(user))
    return _public_user(user)


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    """Who is logged in? Frontend calls this to decide which page to show."""
    return _public_user(current)


@router.post("/logout")
def logout(response: Response):
    """Clear the session cookie."""
    clear_session_cookie(response)
    return {"status": "logged_out", "cookie": SESSION_COOKIE}
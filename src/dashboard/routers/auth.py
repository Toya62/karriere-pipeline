"""FastAPI Router for User Authentication, Registration, and Google OAuth2."""

import os
import re
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from src.core.logger import get_logger
from src.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_google_id_token,
    verify_password,
)
from src.db.database import (
    create_user,
    get_or_create_default_user,
    get_user_by_email,
    get_user_by_google_id,
    get_user_by_id,
    get_user_profile,
    update_user,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$")


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password (min 6 characters)")
    full_name: str = Field("", description="User full name")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class GoogleAuthRequest(BaseModel):
    credential: str = Field(..., description="Google OAuth2 ID Token / Credential string")


class UpdateMeRequest(BaseModel):
    full_name: str | None = None


ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "pandeytoya22@gmail.com").strip().lower()
ADMIN_NAME = os.getenv("ADMIN_NAME", "Toyanath Pandey")


def _clean_user_response(user: dict[str, Any]) -> dict[str, Any]:
    """Sanitize user record for client response by stripping password hashes."""
    safe = dict(user)
    safe.pop("hashed_password", None)
    return safe


def _resolve_user_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve or auto-provision local user from JWT payload (supports local & Supabase)."""
    # 1. Local token with user_id
    if "user_id" in payload:
        return get_user_by_id(payload["user_id"])

    # 2. Supabase token with email / sub
    email = payload.get("email")
    if email:
        email_clean = email.strip().lower()
        user = get_user_by_email(email_clean)
        is_admin_email = email_clean == ADMIN_EMAIL

        if user:
            # Promote configured admin to PRO tier and ADMIN role if not already
            if is_admin_email and (user.get("tier") != "pro" or user.get("role") != "admin"):
                update_user(user["id"], {"tier": "pro", "role": "admin"})
                user = get_user_by_id(user["id"])
            return user

        # Auto-provision user record for first-time Supabase sign-in
        meta = payload.get("user_metadata") or {}
        full_name = ADMIN_NAME if is_admin_email else (meta.get("full_name") or meta.get("name") or email.split("@")[0])
        provider = payload.get("app_metadata", {}).get("provider", "supabase")
        tier = "pro" if is_admin_email else "free"
        role = "admin" if is_admin_email else "candidate"

        user = create_user(
            email=email_clean,
            full_name=full_name,
            auth_provider=provider,
            google_id=payload.get("sub") if provider == "google" else None,
            tier=tier,
            role=role,
        )
        return user

    return None


def get_current_user(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """FastAPI dependency to extract and validate the authenticated user.
    
    If Authorization header is present, validates JWT.
    If header is absent, returns anonymous Guest user with id=0 so zero private candidate data leaks.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = _resolve_user_from_payload(payload)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    # Anonymous guest visitor — zero private data access
    return {
        "id": 0,
        "email": "",
        "full_name": "Guest",
        "auth_provider": "guest",
        "role": "guest",
        "tier": "free",
    }


def require_authenticated_user(
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Strict authentication dependency rejecting unauthenticated requests."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _resolve_user_from_payload(payload)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register")
def register(payload: RegisterRequest):
    """Register a new SaaS user with email and password."""
    email = payload.email.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    hashed_pw = hash_password(payload.password)
    user = create_user(
        email=email,
        hashed_password=hashed_pw,
        full_name=payload.full_name.strip(),
        auth_provider="email",
        tier="free",
    )

    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "role": user.get("role", "candidate"),
    })

    return {
        "success": True,
        "token": token,
        "token_type": "bearer",
        "user": _clean_user_response(user),
    }


@router.post("/login")
def login(payload: LoginRequest):
    """Authenticate with email and password."""
    email = payload.email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(payload.password, user.get("hashed_password")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "role": user.get("role", "candidate"),
    })

    return {
        "success": True,
        "token": token,
        "token_type": "bearer",
        "user": _clean_user_response(user),
    }


@router.post("/google")
def google_auth(payload: GoogleAuthRequest):
    """Sign in or register using Google OAuth2 ID Token."""
    google_data = verify_google_id_token(payload.credential)
    if not google_data or not google_data.get("email"):
        raise HTTPException(status_code=400, detail="Invalid or expired Google authentication credential")

    email = google_data["email"].strip().lower()
    google_id = str(google_data.get("sub", ""))
    full_name = google_data.get("name", "")

    # Look up by google_id or email
    user = get_user_by_google_id(google_id) or get_user_by_email(email)

    if user:
        # Link Google ID if not already linked
        if not user.get("google_id") and google_id:
            update_user(user["id"], {"google_id": google_id, "auth_provider": "google"})
            user = get_user_by_id(user["id"])
    else:
        # Create new Google OAuth user
        user = create_user(
            email=email,
            hashed_password=None,
            full_name=full_name,
            auth_provider="google",
            google_id=google_id,
            tier="free",
        )

    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "role": user.get("role", "candidate"),
    })

    return {
        "success": True,
        "token": token,
        "token_type": "bearer",
        "user": _clean_user_response(user),
    }


@router.get("/me")
def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    """Return profile and metadata for currently authenticated user."""
    if not current_user.get("id") or current_user.get("id") <= 0:
        return {
            "user": None,
            "has_profile": False,
        }
    profile = get_user_profile(current_user["id"])
    return {
        "user": _clean_user_response(current_user),
        "has_profile": profile is not None,
    }


@router.put("/me")
def update_me(payload: UpdateMeRequest, current_user: dict[str, Any] = Depends(require_authenticated_user)):
    """Update current user profile info."""
    updates = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name.strip()
    if updates:
        update_user(current_user["id"], updates)
        current_user = get_user_by_id(current_user["id"])
    return {
        "success": True,
        "user": _clean_user_response(current_user),
    }


@router.get("/supabase-config")
def get_supabase_config():
    """Return public Supabase configuration for client-side GoTrue SDK."""
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_publishable_key": os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
        "configured": bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_PUBLISHABLE_KEY")),
    }


class SetUserTierRequest(BaseModel):
    email: str
    tier: str = "pro"


@router.post("/set-tier")
def set_user_tier(
    payload: SetUserTierRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
):
    """Admin-only endpoint to promote or set a candidate's subscription tier ('pro' | 'free')."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required to change user tiers.")

    target_email = payload.email.strip().lower()
    target_tier = payload.tier.strip().lower()
    if target_tier not in ("free", "pro"):
        raise HTTPException(status_code=400, detail="Invalid tier. Allowed values: 'free', 'pro'.")

    user = get_user_by_email(target_email)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with email '{target_email}' not found.")

    update_user(user["id"], {"tier": target_tier})
    updated_user = get_user_by_id(user["id"])
    return {
        "success": True,
        "email": target_email,
        "tier": target_tier,
        "user": _clean_user_response(updated_user),
    }


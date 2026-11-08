"""FastAPI Router for User Authentication, Registration, and Google OAuth2."""

import os
import re
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from src.core.logger import get_logger
from src.core.notifier import (
    send_admin_new_user_alert,
    send_verification_email,
    send_welcome_email,
)
from src.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_google_id_token,
    verify_password,
)
from src.db.database import (
    create_user,
    create_verification_token,
    get_or_create_default_user,
    get_user_by_email,
    get_user_by_google_id,
    get_user_by_id,
    get_user_profile,
    update_user,
    verify_user_token,
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


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., description="User email address")


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
        is_verified=False,
    )

    # Issue email verification token and dispatch verification link
    token = create_verification_token(user["id"])
    send_verification_email(email=email, name=user.get("full_name", ""), token=token)

    return {
        "success": True,
        "requires_verification": True,
        "message": "Confirmation link sent to your email. Please verify to activate your account.",
        "email": email,
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

    # Gate unverified accounts (Admin is always auto-verified)
    is_admin = (user.get("role") == "admin" or user.get("email") == "pandeytoya22@gmail.com")
    if not is_admin and not bool(user.get("is_verified", False)):
        return JSONResponse(
            status_code=403,
            content={
                "error": "email_unverified",
                "detail": "Please verify your email address before signing in.",
                "message": "Please verify your email address before signing in.",
                "email": email,
            },
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


@router.get("/verify")
def verify_email(token: str = Query(..., description="Email verification token")):
    """Verify candidate email via magic link token, issue JWT session, and redirect to dashboard."""
    if not token or not token.strip():
        return RedirectResponse(url="/?verified=0&error=missing_token", status_code=307)

    user = verify_user_token(token.strip())
    if not user:
        return RedirectResponse(url="/?verified=0&error=invalid_or_expired_token", status_code=307)

    # Dispatch welcome email and admin notification
    send_welcome_email(user["email"], user.get("full_name", ""))
    send_admin_new_user_alert(user)

    # Issue JWT access token for seamless first login
    jwt_token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "role": user.get("role", "candidate"),
    })

    return RedirectResponse(url=f"/?verified=1&token={jwt_token}", status_code=307)


@router.post("/resend-verification")
def resend_verification(payload: ResendVerificationRequest):
    """Resend verification email to an unverified user."""
    email = payload.email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        return {"success": True, "message": "If this email is registered and unverified, a verification link has been sent."}

    if bool(user.get("is_verified", False)):
        return {"success": True, "message": "Email is already verified. Please sign in."}

    token = create_verification_token(user["id"])
    send_verification_email(email=email, name=user.get("full_name", ""), token=token)
    return {"success": True, "message": "Verification email resent successfully."}


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
    is_new = False

    if user:
        updates = {}
        if not user.get("google_id") and google_id:
            updates["google_id"] = google_id
            updates["auth_provider"] = "google"
        if not bool(user.get("is_verified", False)):
            updates["is_verified"] = True
        if updates:
            update_user(user["id"], updates)
            user = get_user_by_id(user["id"])
    else:
        is_new = True
        user = create_user(
            email=email,
            hashed_password=None,
            full_name=full_name,
            auth_provider="google",
            google_id=google_id,
            tier="free",
            is_verified=True,
        )
        send_welcome_email(email, full_name)
        send_admin_new_user_alert(user)

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
        "is_new_user": is_new,
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


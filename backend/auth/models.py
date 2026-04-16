"""
Ask VJ — Auth Pydantic Models

Request/response schemas for OTP login, JWT tokens, and user management.
"""

import re

from pydantic import BaseModel, field_validator


# ── Validators ──

_E164_PATTERN = re.compile(r"^\+91\d{10}$")
_OTP_PATTERN = re.compile(r"^\d{6}$")


def _validate_phone(value: str) -> str:
    if not _E164_PATTERN.match(value):
        raise ValueError("Phone must be in E.164 format: +91XXXXXXXXXX")
    return value


# ── OTP Flow ──


class OTPRequestBody(BaseModel):
    """Request body for POST /auth/request-otp."""
    phone: str

    @field_validator("phone")
    @classmethod
    def phone_e164(cls, v: str) -> str:
        return _validate_phone(v)


class OTPVerifyBody(BaseModel):
    """Request body for POST /auth/verify-otp."""
    phone: str
    otp_code: str

    @field_validator("phone")
    @classmethod
    def phone_e164(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("otp_code")
    @classmethod
    def otp_six_digits(cls, v: str) -> str:
        if not _OTP_PATTERN.match(v):
            raise ValueError("OTP code must be exactly 6 digits")
        return v


# ── Token / User Info ──


class UserInfo(BaseModel):
    """User details returned from JWT decode and /auth/me."""
    user_id: int
    phone: str
    display_name: str
    role: str


class TokenResponse(BaseModel):
    """Response from POST /auth/verify-otp on successful login."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


# ── Admin User Management ──


class UserCreateBody(BaseModel):
    """Request body for POST /auth/admin/users."""
    phone: str
    display_name: str
    role: str = "viewer"

    @field_validator("phone")
    @classmethod
    def phone_e164(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        allowed = {"admin", "viewer", "manager"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v


class UserUpdateBody(BaseModel):
    """Request body for PUT /auth/admin/users/{user_id}."""
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"admin", "viewer", "manager"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v

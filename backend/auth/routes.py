"""
Ask VJ — Auth Routes

OTP-based phone login, token verification, and logout.
Router prefix is handled by main.py (expected: /auth).
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth.db import (
    create_session,
    find_user_by_phone,
    revoke_session,
    store_otp,
    update_last_login,
    verify_otp,
)
from backend.auth.dependencies import get_current_user
from backend.auth.jwt_handler import create_access_token
from backend.auth.models import (
    OTPRequestBody,
    OTPVerifyBody,
    TokenResponse,
    UserInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/request-otp")
async def request_otp(body: OTPRequestBody, request: Request):
    """
    Send a 6-digit OTP to the given phone number.

    The user must already exist and be active.
    """
    config = request.app.state.config
    engine = request.app.state.auth_engine
    gateway = request.app.state.otp_gateway

    # Check user exists and is active
    user = find_user_by_phone(engine, body.phone)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for this phone number",
        )
    if not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Generate and store OTP
    if config.auth.otp_gateway == "mock":
        otp_code = "123456"
    else:
        otp_code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=config.auth.otp_expiry_minutes,
    )
    store_otp(engine, body.phone, otp_code, expires_at)

    # Send via gateway
    sent = await gateway.send_otp(body.phone, otp_code)
    if not sent:
        logger.error("Failed to send OTP to %s", body.phone)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send OTP. Please try again.",
        )

    return {"status": "otp_sent"}


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp_endpoint(body: OTPVerifyBody, request: Request):
    """
    Verify an OTP code and return a JWT access token on success.
    """
    config = request.app.state.config
    engine = request.app.state.auth_engine

    # Verify the OTP
    if not verify_otp(engine, body.phone, body.otp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    # Load user
    user = find_user_by_phone(engine, body.phone)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Create JWT
    jti = str(uuid4())
    expiry_hours = config.auth.jwt_expiry_hours
    token = create_access_token(
        user_id=user["user_id"],
        role=user["role"],
        jti=jti,
        secret=config.auth.jwt_secret_key,
        expiry_hours=expiry_hours,
    )

    # Store session for revocation support
    session_expires = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
    create_session(engine, user["user_id"], jti, session_expires)

    # Update last login timestamp
    update_last_login(engine, user["user_id"])

    return TokenResponse(
        access_token=token,
        expires_in=expiry_hours * 3600,
        user=UserInfo(
            user_id=user["user_id"],
            phone=user["phone"],
            display_name=user["display_name"],
            role=user["role"],
        ),
    )


@router.post("/logout")
async def logout(request: Request, user: UserInfo = Depends(get_current_user)):
    """
    Revoke the current session (invalidates the JWT).
    """
    engine = request.app.state.auth_engine

    # Extract jti from the token to revoke the session
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()

    from backend.auth.jwt_handler import decode_token

    config = request.app.state.config
    claims = decode_token(token, config.auth.jwt_secret_key)
    revoke_session(engine, claims["jti"])

    logger.info("User %d logged out (jti=%s)", user.user_id, claims["jti"])
    return {"status": "logged_out"}


@router.get("/me", response_model=UserInfo)
async def get_me(user: UserInfo = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return user

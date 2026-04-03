"""
Ask VJ — FastAPI Auth Dependencies

Reusable dependencies for extracting and validating the current user
from the Authorization header JWT.
"""

import logging

from fastapi import Depends, HTTPException, Request, status

from backend.auth.jwt_handler import decode_token
from backend.auth.db import is_session_valid, find_user_by_id
from backend.auth.models import UserInfo

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> UserInfo:
    """
    Extract Bearer token from the Authorization header, decode the JWT,
    validate the session in the database, and return a UserInfo object.

    Raises HTTPException(401) on any failure.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.removeprefix("Bearer ").strip()
    config = request.app.state.config
    engine = request.app.state.auth_engine

    # Decode and validate JWT
    try:
        claims = decode_token(token, config.auth.jwt_secret_key)
    except ValueError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check session is still valid (not revoked, not expired)
    jti = claims.get("jti")
    if not jti or not is_session_valid(engine, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load full user record
    user_id = int(claims["sub"])
    user = find_user_by_id(engine, user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserInfo(
        user_id=user["user_id"],
        phone=user["phone"],
        display_name=user["display_name"],
        role=user["role"],
    )


async def require_admin(
    user: UserInfo = Depends(get_current_user),
) -> UserInfo:
    """
    Dependency that requires the current user to have the 'admin' role.

    Raises HTTPException(403) if the user is not an admin.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user

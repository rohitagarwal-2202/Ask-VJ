"""
Ask VJ — JWT Token Handler

Creates and validates HS256 JWT access tokens for authenticated sessions.
"""

from datetime import datetime, timedelta, timezone

import jwt


def create_access_token(
    user_id: int,
    role: str,
    jti: str,
    secret: str,
    expiry_hours: int = 24,
) -> str:
    """
    Create an HS256 JWT with standard claims.

    Claims:
        sub  — user_id (as string per JWT spec)
        role — user role (admin, viewer, manager)
        jti  — unique token identifier for session tracking / revocation
        iat  — issued-at timestamp
        exp  — expiration timestamp
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(hours=expiry_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    """
    Validate signature and expiry, then return the decoded claims.

    Raises:
        ValueError: If the token is invalid, expired, or has a bad signature.
    """
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
        return claims
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")

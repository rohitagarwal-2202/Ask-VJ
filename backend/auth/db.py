"""
Ask VJ — Auth Database Access

All auth-related SQL operations against the app schema in the warehouse.
Uses SQLAlchemy Core with text() queries for clarity and control.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ── Engine ──


def get_engine(config) -> Engine:
    """Create a SQLAlchemy engine from the warehouse connection config."""
    return create_engine(
        config.warehouse.connection_string,
        pool_pre_ping=True,
    )


# ── Users ──


def find_user_by_phone(engine: Engine, phone: str) -> dict | None:
    """Look up a user by E.164 phone number. Returns None if not found."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_id, phone, display_name, role, is_active,
                       created_at, updated_at, last_login_at
                FROM app.users
                WHERE phone = :phone
            """),
            {"phone": phone},
        ).mappings().fetchone()
    return dict(row) if row else None


def find_user_by_id(engine: Engine, user_id: int) -> dict | None:
    """Look up a user by primary key. Returns None if not found."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_id, phone, display_name, role, is_active,
                       created_at, updated_at, last_login_at
                FROM app.users
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).mappings().fetchone()
    return dict(row) if row else None


def create_user(
    engine: Engine,
    phone: str,
    display_name: str,
    role: str,
    created_by: int | None = None,
) -> dict:
    """Insert a new user and return the created record."""
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO app.users (phone, display_name, role, created_by)
                VALUES (:phone, :display_name, :role, :created_by)
                RETURNING user_id, phone, display_name, role, is_active,
                          created_at, updated_at, last_login_at
            """),
            {
                "phone": phone,
                "display_name": display_name,
                "role": role,
                "created_by": created_by,
            },
        ).mappings().fetchone()
    return dict(row)


def update_user(engine: Engine, user_id: int, **kwargs) -> dict | None:
    """
    Update user fields. Accepts keyword arguments matching column names:
    display_name, role, is_active.
    Returns the updated record or None if user not found.
    """
    allowed = {"display_name", "role", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return find_user_by_id(engine, user_id)

    set_clauses = ", ".join(f"{col} = :{col}" for col in updates)
    updates["user_id"] = user_id

    with engine.begin() as conn:
        row = conn.execute(
            text(f"""
                UPDATE app.users
                SET {set_clauses}, updated_at = NOW()
                WHERE user_id = :user_id
                RETURNING user_id, phone, display_name, role, is_active,
                          created_at, updated_at, last_login_at
            """),
            updates,
        ).mappings().fetchone()
    return dict(row) if row else None


def list_users(engine: Engine) -> list[dict]:
    """Return all users ordered by user_id."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT user_id, phone, display_name, role, is_active,
                       created_at, updated_at, last_login_at
                FROM app.users
                ORDER BY user_id
            """)
        ).mappings().fetchall()
    return [dict(r) for r in rows]


# ── OTP ──


def store_otp(engine: Engine, phone: str, otp_code: str, expires_at: datetime) -> int:
    """Store a new OTP request and return the otp_id."""
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO app.otp_requests (phone, otp_code, expires_at)
                VALUES (:phone, :otp_code, :expires_at)
                RETURNING otp_id
            """),
            {"phone": phone, "otp_code": otp_code, "expires_at": expires_at},
        ).fetchone()
    return row[0]


def verify_otp(engine: Engine, phone: str, otp_code: str) -> bool:
    """
    Verify an OTP code for the given phone number.

    Checks that the OTP:
    - Matches the phone and code
    - Has not expired
    - Has not already been verified
    - Has fewer than max attempts (enforced at app layer via config)

    Increments the attempt counter on every verification try.
    On success, marks the OTP as verified.
    Returns True if the OTP is valid.
    """
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        # Increment attempts and fetch the latest matching OTP
        row = conn.execute(
            text("""
                UPDATE app.otp_requests
                SET attempts = attempts + 1
                WHERE otp_id = (
                    SELECT otp_id FROM app.otp_requests
                    WHERE phone = :phone
                      AND verified = false
                      AND expires_at > :now
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                RETURNING otp_id, otp_code, attempts
            """),
            {"phone": phone, "now": now},
        ).mappings().fetchone()

        if row is None:
            return False

        if row["otp_code"] != otp_code:
            return False

        # Mark as verified
        conn.execute(
            text("UPDATE app.otp_requests SET verified = true WHERE otp_id = :otp_id"),
            {"otp_id": row["otp_id"]},
        )
        return True


# ── Sessions ──


def create_session(
    engine: Engine,
    user_id: int,
    jwt_jti: str,
    expires_at: datetime,
) -> str:
    """Create a new session and return the session_id (UUID)."""
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO app.sessions (user_id, jwt_jti, expires_at)
                VALUES (:user_id, :jwt_jti, :expires_at)
                RETURNING session_id::text
            """),
            {"user_id": user_id, "jwt_jti": jwt_jti, "expires_at": expires_at},
        ).fetchone()
    return row[0]


def is_session_valid(engine: Engine, jti: str) -> bool:
    """Check if a session exists, is not revoked, and has not expired."""
    now = datetime.now(timezone.utc)
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT 1 FROM app.sessions
                WHERE jwt_jti = :jti
                  AND revoked = false
                  AND expires_at > :now
            """),
            {"jti": jti, "now": now},
        ).fetchone()
    return row is not None


def revoke_session(engine: Engine, jti: str) -> None:
    """Mark a session as revoked."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE app.sessions SET revoked = true WHERE jwt_jti = :jti"),
            {"jti": jti},
        )


def update_last_login(engine: Engine, user_id: int) -> None:
    """Set last_login_at to current time."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE app.users SET last_login_at = NOW() WHERE user_id = :user_id"),
            {"user_id": user_id},
        )

"""
Ask VJ — Admin User Management Routes

All endpoints require the 'admin' role.
Router prefix is handled by main.py (expected: /auth/admin).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth.db import (
    create_user,
    find_user_by_id,
    list_users,
    update_user,
)
from backend.auth.dependencies import require_admin
from backend.auth.models import UserCreateBody, UserInfo, UserUpdateBody

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users")
async def get_users(
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """List all users."""
    engine = request.app.state.auth_engine
    users = list_users(engine)
    return {"users": users}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    body: UserCreateBody,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Create a new user (admin only)."""
    engine = request.app.state.auth_engine

    try:
        user = create_user(
            engine,
            phone=body.phone,
            display_name=body.display_name,
            role=body.role,
            created_by=admin.user_id,
        )
    except Exception as exc:
        # Unique constraint violation on phone
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this phone number already exists",
            )
        logger.exception("Failed to create user")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )

    logger.info(
        "Admin %d created user %d (%s)",
        admin.user_id, user["user_id"], body.phone,
    )
    return user


@router.put("/users/{user_id}")
async def update_existing_user(
    user_id: int,
    body: UserUpdateBody,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Update an existing user's display_name, role, or is_active status."""
    engine = request.app.state.auth_engine

    # Verify target user exists
    existing = find_user_by_id(engine, user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return existing

    updated = update_user(engine, user_id, **updates)
    logger.info("Admin %d updated user %d: %s", admin.user_id, user_id, updates)
    return updated


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Soft-delete a user by setting is_active=false."""
    engine = request.app.state.auth_engine

    existing = find_user_by_id(engine, user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent admin from deactivating themselves
    if user_id == admin.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    update_user(engine, user_id, is_active=False)
    logger.info("Admin %d deactivated user %d", admin.user_id, user_id)
    return {"status": "deactivated", "user_id": user_id}

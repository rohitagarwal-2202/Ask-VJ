"""
Ask VJ — Admin API for Data Policy Management

CRUD endpoints for managing per-user data access policies.
All routes require the 'admin' role.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from backend.auth.dependencies import require_admin
from backend.auth.models import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ──

class PolicyBody(BaseModel):
    """Request body for creating or updating a policy."""
    policy_type: str   # project_filter, table_access, column_mask
    target: str        # table name, column ref, etc.
    action: str        # allow, deny, mask
    value: dict | None = None  # e.g. {"project_keys": [1, 2, 3]}


class PolicyResponse(BaseModel):
    """Single policy record."""
    policy_id: int
    user_id: int
    policy_type: str
    target: str
    action: str
    value: dict | None
    created_at: str


class TemplateResponse(BaseModel):
    """Single policy template record."""
    template_id: int
    template_name: str
    description: str | None
    policies: list[dict]


# ── Routes ──

@router.get("/users/{user_id}/policies", response_model=list[PolicyResponse])
async def list_user_policies(
    user_id: int,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """List all data policies for a user."""
    engine = request.app.state.auth_engine
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT policy_id, user_id, policy_type, target, action, value, "
                "created_at FROM app.data_policies WHERE user_id = :uid "
                "ORDER BY policy_id"
            ),
            {"uid": user_id},
        ).fetchall()

    return [
        PolicyResponse(
            policy_id=r[0],
            user_id=r[1],
            policy_type=r[2],
            target=r[3],
            action=r[4],
            value=r[5],
            created_at=r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
        )
        for r in rows
    ]


@router.post(
    "/users/{user_id}/policies",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_policy(
    user_id: int,
    body: PolicyBody,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Add a data policy for a user."""
    engine = request.app.state.auth_engine
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO app.data_policies (user_id, policy_type, target, action, value, updated_by) "
                "VALUES (:uid, :ptype, :target, :action, :value::jsonb, :admin_id) "
                "RETURNING policy_id, user_id, policy_type, target, action, value, created_at"
            ),
            {
                "uid": user_id,
                "ptype": body.policy_type,
                "target": body.target,
                "action": body.action,
                "value": _json_dumps(body.value),
                "admin_id": admin.user_id,
            },
        ).fetchone()

    return PolicyResponse(
        policy_id=row[0],
        user_id=row[1],
        policy_type=row[2],
        target=row[3],
        action=row[4],
        value=row[5],
        created_at=row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
    )


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: int,
    body: PolicyBody,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Update an existing data policy."""
    engine = request.app.state.auth_engine
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE app.data_policies "
                "SET policy_type = :ptype, target = :target, action = :action, "
                "    value = :value::jsonb, updated_by = :admin_id "
                "WHERE policy_id = :pid "
                "RETURNING policy_id, user_id, policy_type, target, action, value, created_at"
            ),
            {
                "pid": policy_id,
                "ptype": body.policy_type,
                "target": body.target,
                "action": body.action,
                "value": _json_dumps(body.value),
                "admin_id": admin.user_id,
            },
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")

    return PolicyResponse(
        policy_id=row[0],
        user_id=row[1],
        policy_type=row[2],
        target=row[3],
        action=row[4],
        value=row[5],
        created_at=row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
    )


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: int,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Delete a data policy."""
    engine = request.app.state.auth_engine
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM app.data_policies WHERE policy_id = :pid"),
            {"pid": policy_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Policy not found")


@router.get("/policy-templates", response_model=list[TemplateResponse])
async def list_templates(
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """List all policy templates."""
    engine = request.app.state.auth_engine
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT template_id, template_name, description, policies "
                "FROM app.policy_templates ORDER BY template_id"
            )
        ).fetchall()

    return [
        TemplateResponse(
            template_id=r[0],
            template_name=r[1],
            description=r[2],
            policies=r[3] if isinstance(r[3], list) else [],
        )
        for r in rows
    ]


@router.post(
    "/users/{user_id}/apply-template/{template_id}",
    response_model=list[PolicyResponse],
    status_code=status.HTTP_201_CREATED,
)
async def apply_template(
    user_id: int,
    template_id: int,
    request: Request,
    admin: UserInfo = Depends(require_admin),
):
    """Apply all policies from a template to a user."""
    engine = request.app.state.auth_engine

    with engine.begin() as conn:
        # Fetch template
        tmpl_row = conn.execute(
            text("SELECT policies FROM app.policy_templates WHERE template_id = :tid"),
            {"tid": template_id},
        ).fetchone()

        if not tmpl_row:
            raise HTTPException(status_code=404, detail="Template not found")

        policies_def = tmpl_row[0]
        if not isinstance(policies_def, list):
            raise HTTPException(status_code=400, detail="Template has no valid policies")

        # Insert each policy from the template
        created = []
        for p in policies_def:
            row = conn.execute(
                text(
                    "INSERT INTO app.data_policies (user_id, policy_type, target, action, value, updated_by) "
                    "VALUES (:uid, :ptype, :target, :action, :value::jsonb, :admin_id) "
                    "RETURNING policy_id, user_id, policy_type, target, action, value, created_at"
                ),
                {
                    "uid": user_id,
                    "ptype": p.get("policy_type", ""),
                    "target": p.get("target", ""),
                    "action": p.get("action", ""),
                    "value": _json_dumps(p.get("value")),
                    "admin_id": admin.user_id,
                },
            ).fetchone()
            created.append(PolicyResponse(
                policy_id=row[0],
                user_id=row[1],
                policy_type=row[2],
                target=row[3],
                action=row[4],
                value=row[5],
                created_at=row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
            ))

    return created


def _json_dumps(value: dict | None) -> str | None:
    """Serialize dict to JSON string for JSONB parameter, or None."""
    if value is None:
        return None
    import json
    return json.dumps(value)

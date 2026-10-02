"""RBAC endpoints (docs/03_API_CONTRACT.md section 6)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.context import Ctx, require
from app.core.authz import ALL_PERMISSION_CODES, PERMISSION_CATALOG
from app.core.errors import NotFound, RuleViolation, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.modules.rbac import service as rbac_service
from app.modules.rbac.models import Role, RolePermission, UserRole

router = APIRouter(tags=["rbac"])


class RoleCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    is_assignable: bool | None = None


class RolePermissionsRequest(BaseModel):
    permission_codes: list[str]
    reason: str = Field(min_length=1, max_length=500)


def _role_payload(role: Role, *, permissions: list[str] | None = None, user_count: int | None = None) -> dict:
    payload = {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "is_assignable": role.is_assignable,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }
    if permissions is not None:
        payload["permissions"] = permissions
        payload["permission_count"] = len(permissions)
    if user_count is not None:
        payload["user_count"] = user_count
    return payload


@router.get("/roles")
async def list_roles(
    include_system: bool = Query(True),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("role.read")),
) -> dict:
    stmt = select(Role).order_by(Role.code)
    count_stmt = select(func.count()).select_from(Role)
    if not include_system:
        stmt = stmt.where(Role.is_system.is_(False))
        count_stmt = count_stmt.where(Role.is_system.is_(False))
    total = int((await ctx.session.execute(count_stmt)).scalar_one())
    rows = list(
        (await ctx.session.execute(stmt.offset(params.offset).limit(params.page_size))).scalars().all()
    )
    counts = dict(
        (
            await ctx.session.execute(
                select(RolePermission.role_id, func.count())
                .where(RolePermission.role_id.in_([row.id for row in rows] or [uuid.uuid4()]))
                .group_by(RolePermission.role_id)
            )
        ).all()
    )
    items = []
    for row in rows:
        item = _role_payload(row)
        item["permission_count"] = int(counts.get(row.id, 0))
        items.append(item)
    return paginated(items, total, params)


@router.post("/roles", status_code=201)
async def create_role(payload: RoleCreateRequest, ctx: Ctx = Depends(require("role.manage"))) -> dict:
    role = await rbac_service.create_role(
        ctx.session,
        code=payload.code.upper(),
        name=payload.name,
        description=payload.description,
        permission_codes=payload.permission_codes,
        actor_user_id=ctx.actor_user_id,
    )
    permissions = await rbac_service.role_permission_codes(ctx.session, role.id)
    await ctx.audit(
        category="PERMISSION",
        action="rbac.role.created",
        entity_type="role",
        entity_id=role.id,
        after={"code": role.code, "permissions": permissions},
    )
    return _role_payload(role, permissions=permissions, user_count=0)


@router.get("/roles/{role_id}")
async def get_role(role_id: uuid.UUID, ctx: Ctx = Depends(require("role.read"))) -> dict:
    role = await rbac_service.get_role(ctx.session, role_id)
    permissions = await rbac_service.role_permission_codes(ctx.session, role.id)
    user_count = int(
        (
            await ctx.session.execute(
                select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id)
            )
        ).scalar_one()
    )
    return _role_payload(role, permissions=permissions, user_count=user_count)


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: uuid.UUID, payload: RoleUpdateRequest, ctx: Ctx = Depends(require("role.manage"))
) -> dict:
    role = await rbac_service.get_role(ctx.session, role_id)
    if role.is_system and payload.name is not None and payload.name != role.name:
        raise RuleViolation(
            "System role names cannot be changed.", rule_code="SYSTEM_ROLE_PROTECTED"
        )
    before = {"name": role.name, "description": role.description, "is_assignable": role.is_assignable}
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.is_assignable is not None:
        role.is_assignable = payload.is_assignable
    await ctx.session.flush()
    permissions = await rbac_service.role_permission_codes(ctx.session, role.id)
    await ctx.audit(
        category="PERMISSION",
        action="rbac.role.updated",
        entity_type="role",
        entity_id=role.id,
        before=before,
        after={"name": role.name, "description": role.description, "is_assignable": role.is_assignable},
    )
    return _role_payload(role, permissions=permissions)


@router.put("/roles/{role_id}/permissions")
async def set_permissions(
    role_id: uuid.UUID, payload: RolePermissionsRequest, ctx: Ctx = Depends(require("role.manage"))
) -> dict:
    role = await rbac_service.get_role(ctx.session, role_id)
    before = await rbac_service.role_permission_codes(ctx.session, role.id)
    if role.code == rbac_service.ADMIN_ROLE_CODE:
        losing = ALL_PERMISSION_CODES - set(payload.permission_codes)
        if losing:
            raise RuleViolation(
                "The ADMIN role must retain the full permission catalog.",
                rule_code="ADMIN_ROLE_MINIMUM",
            )
    await rbac_service.set_role_permissions(
        ctx.session, role, payload.permission_codes, actor_user_id=ctx.actor_user_id
    )
    after = await rbac_service.role_permission_codes(ctx.session, role.id)
    await ctx.audit(
        category="PERMISSION",
        action="rbac.role.permissions_changed",
        entity_type="role",
        entity_id=role.id,
        before={"permissions": before},
        after={"permissions": after},
        reason=payload.reason,
    )
    return _role_payload(role, permissions=after)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: uuid.UUID, ctx: Ctx = Depends(require("role.manage"))) -> Response:
    role = await rbac_service.get_role(ctx.session, role_id)
    await rbac_service.delete_role(ctx.session, role)
    await ctx.audit(
        category="PERMISSION",
        action="rbac.role.deleted",
        entity_type="role",
        entity_id=role_id,
        before={"code": role.code, "name": role.name},
    )
    return Response(status_code=204)


@router.get("/permissions")
async def list_permissions(
    module: str | None = Query(None), ctx: Ctx = Depends(require("permission.read"))
) -> dict:
    items = [
        {
            "code": code,
            "module": module_name,
            "is_sensitive": is_sensitive,
            "description": description,
        }
        for code, module_name, is_sensitive, description in PERMISSION_CATALOG
        if not module or module_name == module
    ]
    return {"items": items, "total": len(items)}
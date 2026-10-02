"""Settings endpoints (docs/03_API_CONTRACT.md section 7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.context import Ctx, require
from app.core.errors import ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.modules.settings import service as settings_service
from app.modules.settings.models import BusinessSetting
from app.modules.settings.registry import SETTINGS_BY_KEY

router = APIRouter(tags=["settings"])


class SettingValue(BaseModel):
    value: Any


class SettingsBulkUpdate(BaseModel):
    changes: dict[str, Any]
    reason: str = Field(min_length=1, max_length=500)


def _describe(definition, current: Any) -> dict:
    return {
        "key": definition.key,
        "value": settings_service.json_safe(current if current is not None else definition.default),
        "value_type": definition.value_type,
        "group": definition.group,
        "description": definition.description,
        "is_provisional": definition.provisional,
        "minimum": definition.minimum,
        "maximum": definition.maximum,
        "allowed": list(definition.allowed) if definition.allowed else None,
    }


@router.get("/settings")
async def list_settings(
    group: str | None = Query(None), ctx: Ctx = Depends(require("settings.read"))
) -> dict:
    rows = {
        row.key: row
        for row in (await ctx.session.execute(select(BusinessSetting))).scalars().all()
    }
    items = []
    for definition in SETTINGS_BY_KEY.values():
        if group and definition.group != group:
            continue
        row = rows.get(definition.key)
        entry = _describe(definition, row.value if row else None)
        entry["version"] = int(row.version) if row else 0
        items.append(entry)
    return {"items": items, "total": len(items)}


@router.get("/settings/schema")
async def settings_schema(ctx: Ctx = Depends(require("settings.read"))) -> dict:
    items = [
        {
            "key": definition.key,
            "value_type": definition.value_type,
            "description": definition.description,
            "default": settings_service.json_safe(definition.default),
            "min": definition.minimum,
            "max": definition.maximum,
            "allowed_values": list(definition.allowed) if definition.allowed else None,
            "unit": None,
            "is_provisional": definition.provisional,
            "consumer_module": definition.group,
            "group": definition.group,
            "affects_history": getattr(definition, "affects_history", False),
        }
        for definition in SETTINGS_BY_KEY.values()
    ]
    return {"items": items, "total": len(items)}


@router.get("/settings/history")
async def settings_history(
    key: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("settings.read.history")),
) -> dict:
    rows = await settings_service.SettingsService(ctx.session).history(key)
    total = len(rows)
    window = rows[params.offset : params.offset + params.page_size]
    items = [
        {
            "id": row.id,
            "setting_key": row.setting_key,
            "setting_version": row.setting_version,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "value_type": row.value_type,
            "changed_by": row.changed_by,
            "reason": row.reason,
            "changed_at": row.changed_at,
        }
        for row in window
    ]
    return paginated(items, total, params)


@router.get("/settings/{key}")
async def get_setting(key: str, ctx: Ctx = Depends(require("settings.read"))) -> dict:
    definition = SETTINGS_BY_KEY.get(key)
    if definition is None:
        raise ValidationError(f"Unknown setting key: {key}")
    row = (
        await ctx.session.execute(select(BusinessSetting).where(BusinessSetting.key == key))
    ).scalar_one_or_none()
    entry = _describe(definition, row.value if row else None)
    entry["version"] = int(row.version) if row else 0
    return entry


@router.put("/settings/{key}")
async def update_setting(
    key: str, payload: SettingValue, ctx: Ctx = Depends(require("settings.update"))
) -> dict:
    service = settings_service.SettingsService(ctx.session)
    row = await service.update(key, payload.value, actor_user_id=ctx.actor_user_id)
    await ctx.audit(
        category="SETTINGS",
        action="settings.updated",
        entity_type="business_setting",
        entity_id=row.id,
        after={"key": key, "value": row.value, "version": row.version},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "settings.changed.v1",
        aggregate_type="business_setting",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"key": key, "version": row.version},
    )
    definition = SETTINGS_BY_KEY[key]
    entry = _describe(definition, row.value)
    entry["version"] = int(row.version)
    return entry


@router.patch("/settings")
async def bulk_update_settings(
    payload: SettingsBulkUpdate, ctx: Ctx = Depends(require("settings.update"))
) -> dict:
    service = settings_service.SettingsService(ctx.session)
    updated = []
    for key, value in payload.changes.items():
        row = await service.update(
            key, value, actor_user_id=ctx.actor_user_id, reason=payload.reason
        )
        updated.append({"key": key, "value": row.value, "version": int(row.version)})
        await ctx.audit(
            category="SETTINGS",
            action="settings.updated",
            entity_type="business_setting",
            entity_id=row.id,
            after={"key": key, "value": row.value},
            reason=payload.reason,
        )
    return {"items": updated, "total": len(updated)}
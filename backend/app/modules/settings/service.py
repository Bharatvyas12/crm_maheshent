"""Business settings service: the only source of configurable business values.

Nothing outside `settings.registry` may invent a business value, and no business
value may be read from the environment (docs/04_BUSINESS_RULES.md section 3).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import time as time_type
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditRecord
from app.core.errors import NotFound, RuleViolation, ValidationError
from app.modules.settings.models import BusinessSetting, BusinessSettingHistory
from app.modules.settings.registry import SETTINGS_BY_KEY, SettingDef

# Settings an ordinary employee may see in the session payload (no financial policy).
EMPLOYEE_VISIBLE_KEYS: tuple[str, ...] = (
    "org.name",
    "org.timezone",
    "org.currency",
    "org.week_starts_on",
    "attendance.verification_mode",
    "attendance.checkout_verification_mode",
    "attendance.shift_tracking_enabled",
    "attendance.shift_start_time",
    "attendance.shift_end_time",
    "attendance.shift_crosses_midnight",
    "attendance.required_daily_hours",
    "attendance.full_day_min_hours",
    "attendance.half_day_min_hours",
    "attendance.partial_day_min_hours",
    "attendance.break_tracking_enabled",
    "attendance.break_max_minutes_per_day",
    "attendance.auto_break_deduction_minutes",
    "attendance.field_work_allowed",
    "attendance.correction_requires_approval",
    "attendance.correction_max_backdate_days",
    "attendance.overtime_enabled",
    "attendance.late_grace_minutes",
    "attendance.early_checkout_grace_minutes",
    "orders.claim_timeout_minutes",
    "orders.max_active_claims_per_employee",
    "orders.claim_requires_active_attendance",
    "orders.pod_required",
    "leaves.enabled",
    "leaves.allow_half_day",
    "complaints.enabled",
    "notifications.channels_enabled",
    "notifications.web_push_enabled",
    "files.max_upload_mb",
    "files.allowed_mime_types",
)


def coerce_value(definition: SettingDef, raw: Any) -> Any:
    """Validate and normalise a raw value for the given setting definition."""
    if raw is None and definition.default is None:
        return None
    value_type = definition.value_type
    if value_type == "INT" or value_type == "DURATION_SECONDS":
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            raise ValidationError(f"Setting {definition.key} expects an integer.")
        try:
            value: Any = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Setting {definition.key} expects an integer.") from exc
    elif value_type == "DECIMAL":
        if isinstance(raw, float):
            raise ValidationError("Floating point values are not accepted; send a decimal string.")
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError(f"Setting {definition.key} expects a decimal.") from exc
        value = value.normalize()
        if value == Decimal("-1").normalize() or value.is_nan():
            raise ValidationError(f"Setting {definition.key} expects a finite decimal.")
        value = Decimal(str(raw)).quantize(Decimal("0.0001")) if value.as_tuple().exponent < -4 else value
    elif value_type == "BOOL":
        if isinstance(raw, bool):
            value = raw
        elif isinstance(raw, str) and raw.strip().lower() in {"true", "false"}:
            value = raw.strip().lower() == "true"
        else:
            raise ValidationError(f"Setting {definition.key} expects true or false.")
    elif value_type == "TIME":
        try:
            hour, _, minute = str(raw).partition(":")
            value = f"{int(hour):02d}:{int(minute or 0):02d}"
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Setting {definition.key} expects HH:MM.") from exc
    elif value_type == "TIMEZONE":
        text = str(raw)
        try:
            ZoneInfo(text)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError(f"Setting {definition.key} expects an IANA timezone.") from exc
        value = text
    elif value_type == "JSON":
        value = raw
        json.dumps(value)
    else:
        value = str(raw)

    if definition.allowed is not None and value not in definition.allowed:
        raise ValidationError(
            f"Setting {definition.key} must be one of: " + ", ".join(str(x) for x in definition.allowed)
        )
    if definition.minimum is not None and value < definition.minimum:
        raise ValidationError(f"Setting {definition.key} must be >= {definition.minimum}.")
    if definition.maximum is not None and value > definition.maximum:
        raise ValidationError(f"Setting {definition.key} must be <= {definition.maximum}.")
    return value


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, time_type):
        return value.strftime("%H:%M")
    return value

class SettingsView:
    """Immutable view of effective settings for one request/transaction."""

    __slots__ = ("_values",)

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, key: str, default: Any = None) -> Any:
        if key not in SETTINGS_BY_KEY:
            raise ValidationError(f"Unknown setting key: {key}")
        value = self._values.get(key)
        return SETTINGS_BY_KEY[key].default if value is None else value

    def raw(self, key: str) -> Any:
        return self._values.get(key, SETTINGS_BY_KEY[key].default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)

    def subset(self, keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: json_safe(self.get(key)) for key in keys}

    def employee_payload(self) -> dict[str, Any]:
        raw = self.subset(EMPLOYEE_VISIBLE_KEYS)
        # The frontend reads `business_timezone` and `currency` (flat names).
        # Map from the canonical dot-notation keys so both forms are present.
        raw["business_timezone"] = raw.get("org.timezone", "UTC")
        raw["currency"] = raw.get("org.currency", "INR")
        return raw

    def int_(self, key: str) -> int:
        return int(self.get(key))

    def decimal_(self, key: str) -> Decimal:
        return Decimal(str(self.get(key)))

    def bool_(self, key: str) -> bool:
        value = self.get(key)
        return bool(value)

    def str_(self, key: str) -> str:
        return str(self.get(key))

    def json_(self, key: str) -> Any:
        return self.get(key)

    def time_(self, key: str) -> time_type:
        raw = str(self.get(key))
        hour, _, minute = raw.partition(":")
        return time_type(int(hour), int(minute or 0))

    def timezone(self) -> ZoneInfo:
        return ZoneInfo(str(self.get("org.timezone")))

    def currency(self) -> str:
        return str(self.get("org.currency"))


class SettingsService:
    """Loads and mutates the DB-backed business settings layer."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load(self) -> SettingsView:
        rows = (await self.session.execute(select(BusinessSetting))).scalars().all()
        values: dict[str, Any] = {}
        for row in rows:
            if row.key not in SETTINGS_BY_KEY:
                continue
            values[row.key] = self._decode(row.value)
        return SettingsView(values)

    @staticmethod
    def _decode(value: Any) -> Any:
        return value

    async def get_row(self, key: str) -> BusinessSetting:
        if key not in SETTINGS_BY_KEY:
            raise NotFound(f"Unknown setting key: {key}")
        row = (
            await self.session.execute(select(BusinessSetting).where(BusinessSetting.key == key))
        ).scalar_one_or_none()
        if row is None:
            raise NotFound(f"Setting {key} has not been initialised.")
        return row

    async def update(
        self,
        key: str,
        raw_value: Any,
        *,
        actor_user_id: uuid.UUID | None,
        reason: str | None = None,
    ) -> BusinessSetting:
        definition = SETTINGS_BY_KEY.get(key)
        if definition is None:
            raise NotFound(f"Unknown setting key: {key}")
        value = coerce_value(definition, raw_value)
        row = (
            await self.session.execute(
                select(BusinessSetting).where(BusinessSetting.key == key).with_for_update()
            )
        ).scalar_one_or_none()
        previous = None
        if row is None:
            row = BusinessSetting(
                key=key,
                value=json_safe(value),
                value_type=definition.value_type,
                description=definition.description,
                is_provisional=definition.provisional,
                version=1,
                updated_by=actor_user_id,
            )
            self.session.add(row)
        else:
            previous = row.value
            row.value = json_safe(value)
            row.value_type = definition.value_type
            row.version = int(row.version or 1) + 1
            row.updated_by = actor_user_id
        await self.session.flush()
        self.session.add(
            BusinessSettingHistory(
                setting_key=key,
                setting_version=row.version,
                old_value=previous,
                new_value=json_safe(value),
                value_type=definition.value_type,
                changed_by=actor_user_id,
                reason=reason,
            )
        )
        await self.session.flush()
        return row

    async def seed_defaults(self, *, actor_user_id: uuid.UUID | None = None) -> int:
        existing = set(
            (await self.session.execute(select(BusinessSetting.key))).scalars().all()
        )
        created = 0
        for definition in SETTINGS_BY_KEY.values():
            if definition.key in existing:
                continue
            self.session.add(
                BusinessSetting(
                    key=definition.key,
                    value=json_safe(definition.default),
                    value_type=definition.value_type,
                    description=definition.description,
                    is_provisional=definition.provisional,
                    version=1,
                    updated_by=actor_user_id,
                )
            )
            created += 1
        await self.session.flush()
        return created

    async def history(self, key: str | None = None) -> list[BusinessSettingHistory]:
        stmt = select(BusinessSettingHistory).order_by(BusinessSettingHistory.changed_at.desc())
        if key:
            stmt = stmt.where(BusinessSettingHistory.setting_key == key)
        return list((await self.session.execute(stmt)).scalars().all())
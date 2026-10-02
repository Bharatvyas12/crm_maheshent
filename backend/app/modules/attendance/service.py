"""Attendance service: verification, state machine, work-hour computation.

Implements docs/04_BUSINESS_RULES.md BR-4.1 .. BR-4.5. The backend is authoritative:
client-supplied verification results, business dates, employee identity and worked
durations are never trusted.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time as time_type, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, RuleViolation, ValidationError
from app.core.money import hours_str
from app.core.timeutil import (
    business_date_of,
    floor_minutes,
    interval_seconds,
    intersect_seconds,
    shift_bounds,
    utcnow,
)
from app.modules.attendance.models import (
    AttendanceCorrection,
    AttendanceEvent,
    AttendanceQrToken,
    AttendanceRecord,
    AttendanceSession,
    AttendanceVerification,
    BreakSession,
    BreakType,
    BusinessHoliday,
)
from app.modules.directory.models import Employee
from app.modules.settings.service import SettingsView

EARTH_RADIUS_M = 6371000.0

GPS_METHODS = {
    "GPS_ONLY": ("GPS",),
    "QR_ONLY": ("QR",),
    "GPS_AND_QR": ("GPS", "QR"),
    "GPS_OR_QR": ("GPS", "QR"),
}


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(slots=True)
class GpsEvidence:
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    accuracy_meters: Decimal | None = None
    location_captured_at: datetime | None = None


@dataclass(slots=True)
class VerificationOutcome:
    method: str
    result: str
    failure_code: str | None = None
    failure_reason: str | None = None
    distance_meters: Decimal | None = None
    accuracy_meters: Decimal | None = None
    geofence_radius_meters: Decimal | None = None
    qr_result: str | None = None
    qr_token_id: uuid.UUID | None = None
    evidence: GpsEvidence = field(default_factory=GpsEvidence)

    @property
    def passed(self) -> bool:
        return self.result in {"PASSED", "PASSED_WITH_WARNING"}


def _dec(value: Any, quant: str) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(quant))


def evaluate_gps(
    settings: SettingsView, evidence: GpsEvidence, *, now: datetime | None = None
) -> VerificationOutcome:
    moment = now or utcnow()
    radius = _dec(settings.get("attendance.geofence_radius_m"), "0.01")
    outcome = VerificationOutcome(
        method="GPS",
        result="FAILED",
        geofence_radius_meters=radius,
        evidence=evidence,
    )
    latitude = settings.get("attendance.geofence_latitude")
    longitude = settings.get("attendance.geofence_longitude")
    if latitude is None or longitude is None:
        outcome.failure_code = "METHOD_NOT_ALLOWED"
        outcome.failure_reason = "The shop location is not configured; GPS check-in cannot pass."
        return outcome
    if (
        evidence.latitude is None
        or evidence.longitude is None
        or evidence.accuracy_meters is None
        or evidence.location_captured_at is None
    ):
        outcome.failure_code = "LOCATION_UNAVAILABLE"
        outcome.failure_reason = "A latitude, longitude, accuracy and capture time are required."
        return outcome
    outcome.accuracy_meters = evidence.accuracy_meters
    captured = evidence.location_captured_at
    if captured.tzinfo is None:
        outcome.failure_code = "LOCATION_STALE"
        outcome.failure_reason = "The location fix must include a timezone offset."
        return outcome
    age = (moment - captured).total_seconds()
    max_age = settings.int_("attendance.location_max_age_seconds")
    if age > max_age or age < -max_age:
        outcome.failure_code = "LOCATION_STALE"
        outcome.failure_reason = f"The location fix is older than {max_age} seconds."
        return outcome
    accuracy_limit = _dec(settings.get("attendance.gps_accuracy_max_m"), "0.01")
    if accuracy_limit is not None and evidence.accuracy_meters > accuracy_limit:
        outcome.failure_code = "ACCURACY_EXCEEDS_LIMIT"
        outcome.failure_reason = (
            f"GPS accuracy {evidence.accuracy_meters} m exceeds the limit of {accuracy_limit} m."
        )
        return outcome
    distance = haversine_meters(
        float(evidence.latitude),
        float(evidence.longitude),
        float(latitude),
        float(longitude),
    )
    outcome.distance_meters = Decimal(str(round(distance, 2)))
    if radius is not None and outcome.distance_meters > radius:
        outcome.failure_code = "OUTSIDE_GEOFENCE"
        outcome.failure_reason = f"You are {outcome.distance_meters} m from the shop."
        return outcome
    outcome.result = "PASSED"
    return outcome


async def consume_qr_token(
    session: AsyncSession,
    settings: SettingsView,
    *,
    qr_payload: str,
    purpose: str,
    employee_id: uuid.UUID,
    method: str = "QR",
) -> VerificationOutcome:
    from app.core.security import sha256_hex

    outcome = VerificationOutcome(method=method, result="FAILED")
    if not qr_payload:
        outcome.failure_code = "QR_MISSING"
        outcome.failure_reason = "A shop QR token is required."
        outcome.qr_result = "INVALID"
        return outcome
    token = (
        await session.execute(
            select(AttendanceQrToken).where(
                AttendanceQrToken.token_hash == sha256_hex(qr_payload)
            )
        )
    ).scalar_one_or_none()
    if token is None:
        outcome.failure_code = "QR_INVALID"
        outcome.failure_reason = "This QR token is not recognised."
        outcome.qr_result = "INVALID"
        return outcome
    outcome.qr_token_id = token.id
    if token.is_revoked:
        outcome.failure_code = "QR_INVALID"
        outcome.failure_reason = "This QR token has been revoked."
        outcome.qr_result = "INVALID"
        return outcome
    if token.purpose != purpose:
        outcome.failure_code = "QR_INVALID"
        outcome.failure_reason = "This QR token is not valid for this action."
        outcome.qr_result = "INVALID"
        return outcome
    now = utcnow()
    if token.expires_at <= now:
        outcome.failure_code = "QR_EXPIRED"
        outcome.failure_reason = "This QR token has expired; rescan the shop display."
        outcome.qr_result = "EXPIRED"
        return outcome
    if settings.bool_("attendance.qr_single_use"):
        if token.consumed_at is not None:
            outcome.failure_code = "QR_REPLAYED"
            outcome.failure_reason = "This QR token has already been used."
            outcome.qr_result = "REPLAYED"
            return outcome
        result = await session.execute(
            update(AttendanceQrToken)
            .where(AttendanceQrToken.id == token.id, AttendanceQrToken.consumed_at.is_(None))
            .values(consumed_at=now, consumed_by_employee_id=employee_id)
        )
        if not result.rowcount:
            outcome.failure_code = "QR_REPLAYED"
            outcome.failure_reason = "This QR token has already been used."
            outcome.qr_result = "REPLAYED"
            return outcome
    outcome.result = "PASSED"
    outcome.qr_result = "VALID"
    return outcome

# ---------------------------------------------------------------------------
# Records and computation
# ---------------------------------------------------------------------------


async def get_record_by_id(session: AsyncSession, record_id: uuid.UUID) -> AttendanceRecord:
    row = await session.get(AttendanceRecord, record_id)
    if row is None:
        raise NotFound("Attendance record not found.")
    return row


async def find_record(
    session: AsyncSession, employee_id: uuid.UUID, business_date: date
) -> AttendanceRecord | None:
    return (
        await session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.business_date == business_date,
            )
        )
    ).scalar_one_or_none()


async def get_or_create_record(
    session: AsyncSession, employee_id: uuid.UUID, business_date: date
) -> AttendanceRecord:
    row = await find_record(session, employee_id, business_date)
    if row is not None:
        return row
    row = AttendanceRecord(
        employee_id=employee_id,
        business_date=business_date,
        status="NOT_MARKED",
        day_classification="NONE",
    )
    session.add(row)
    await session.flush()
    return row


def _hours_decimal(seconds: int) -> Decimal:
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))


def classify_day(settings: SettingsView, status: str, worked_seconds: int) -> str:
    if status in {"ON_LEAVE", "HOLIDAY", "WEEKLY_OFF", "ABSENT"}:
        return "NONE"
    hours = _hours_decimal(worked_seconds)
    if hours >= settings.decimal_("attendance.full_day_min_hours"):
        return "FULL_DAY"
    if hours >= settings.decimal_("attendance.half_day_min_hours"):
        return "HALF_DAY"
    if hours >= settings.decimal_("attendance.partial_day_min_hours"):
        return "PARTIAL_DAY"
    return "NONE"


def compute_overtime_seconds(settings: SettingsView, worked_seconds: int) -> int:
    if not settings.bool_("attendance.overtime_enabled"):
        return 0
    threshold = int(settings.decimal_("attendance.overtime_threshold_hours") * 3600)
    raw = max(0, worked_seconds - threshold)
    step = settings.int_("attendance.overtime_min_minutes") * 60
    if step <= 0:
        return 0
    steps = raw // step
    cap = int(settings.decimal_("attendance.overtime_cap_hours_per_day") * 3600)
    return int(min(steps * step, cap))


def compute_late_early(
    settings: SettingsView,
    business_date: date,
    first_check_in_at: datetime | None,
    last_check_out_at: datetime | None,
) -> tuple[int, int]:
    if not settings.bool_("attendance.shift_tracking_enabled"):
        return 0, 0
    tz = settings.timezone()
    start_at, end_at = shift_bounds(
        business_date,
        settings.time_("attendance.shift_start_time"),
        settings.time_("attendance.shift_end_time"),
        tz,
        settings.bool_("attendance.shift_crosses_midnight"),
    )
    late = 0
    early = 0
    if first_check_in_at is not None:
        grace = timedelta(minutes=settings.int_("attendance.late_grace_minutes"))
        late = floor_minutes(first_check_in_at - (start_at + grace))
    if last_check_out_at is not None:
        grace = timedelta(minutes=settings.int_("attendance.early_checkout_grace_minutes"))
        early = floor_minutes((end_at - grace) - last_check_out_at)
    return late, early


async def recompute_record(
    session: AsyncSession,
    record: AttendanceRecord,
    settings: SettingsView,
    *,
    reason: str = "RECOMPUTE",
) -> dict[str, Any]:
    """Idempotently recompute derived fields; returns {changed, before, after}."""
    before = {
        "status": record.status,
        "day_classification": record.day_classification,
        "worked_seconds": record.worked_seconds,
        "break_seconds": record.break_seconds,
        "unpaid_break_seconds": record.unpaid_break_seconds,
        "overtime_seconds": record.overtime_seconds,
        "late_minutes": record.late_minutes,
        "early_checkout_minutes": record.early_checkout_minutes,
    }
    sessions = list(
        (
            await session.execute(
                select(AttendanceSession).where(
                    AttendanceSession.attendance_record_id == record.id
                )
            )
        ).scalars().all()
    )
    breaks = list(
        (
            await session.execute(
                select(BreakSession).where(BreakSession.attendance_record_id == record.id)
            )
        ).scalars().all()
    )
    closed_sessions = [(row.started_at, row.ended_at) for row in sessions if row.ended_at is not None]
    session_intervals = [(start, end) for start, end in closed_sessions if end is not None]
    session_seconds = interval_seconds(session_intervals)
    all_break_seconds = sum(
        int((row.ended_at - row.started_at).total_seconds())
        for row in breaks
        if row.ended_at is not None
    )
    if settings.bool_("attendance.break_tracking_enabled"):
        unpaid_intervals = [
            (row.started_at, row.ended_at)
            for row in breaks
            if row.ended_at is not None and not row.is_paid
        ]
        unpaid_break_seconds = intersect_seconds(unpaid_intervals, session_intervals)
        worked_seconds = max(0, session_seconds - unpaid_break_seconds)
    else:
        auto = settings.int_("attendance.auto_break_deduction_minutes") * 60
        if auto > 0 and session_seconds > auto:
            worked_seconds = max(0, session_seconds - auto)
        else:
            worked_seconds = session_seconds
        unpaid_break_seconds = 0

    open_session = any(row.ended_at is None for row in sessions)

    first_check_in = min((row.started_at for row in sessions), default=None)
    last_check_out = max(
        (row.ended_at for row in sessions if row.ended_at is not None), default=None
    )

    if open_session:
        status = "INCOMPLETE"
    elif sessions:
        status = "PRESENT"
    elif record.status in {"ON_LEAVE", "HOLIDAY", "WEEKLY_OFF", "ABSENT"}:
        status = record.status
    else:
        status = "NOT_MARKED"

    classification = classify_day(settings, status, worked_seconds)
    overtime = compute_overtime_seconds(settings, worked_seconds)
    late, early = compute_late_early(settings, record.business_date, first_check_in, last_check_out)

    record.first_check_in_at = first_check_in
    record.last_check_out_at = last_check_out
    record.worked_seconds = worked_seconds
    record.break_seconds = all_break_seconds
    record.unpaid_break_seconds = unpaid_break_seconds
    record.overtime_seconds = overtime
    record.late_minutes = late
    record.early_checkout_minutes = early
    record.day_classification = classification
    record.is_open = open_session
    record.status = status
    record.computation_version = int(record.computation_version or 1) + 1
    record.settings_snapshot = snapshot_settings(settings)
    record.computed_at = utcnow()
    record.updated_at = utcnow()
    await session.flush()
    after = {
        "status": status,
        "day_classification": classification,
        "worked_seconds": worked_seconds,
        "break_seconds": all_break_seconds,
        "unpaid_break_seconds": unpaid_break_seconds,
        "overtime_seconds": overtime,
        "late_minutes": late,
        "early_checkout_minutes": early,
    }
    return {"changed": before != after, "before": before, "after": after, "reason": reason}


SNAPSHOT_KEYS = (
    "attendance.verification_mode",
    "attendance.checkout_verification_mode",
    "attendance.geofence_latitude",
    "attendance.geofence_longitude",
    "attendance.geofence_radius_m",
    "attendance.gps_accuracy_max_m",
    "attendance.shift_tracking_enabled",
    "attendance.shift_start_time",
    "attendance.shift_end_time",
    "attendance.shift_crosses_midnight",
    "attendance.required_daily_hours",
    "attendance.full_day_min_hours",
    "attendance.half_day_min_hours",
    "attendance.partial_day_min_hours",
    "attendance.overtime_enabled",
    "attendance.overtime_threshold_hours",
    "attendance.overtime_min_minutes",
    "attendance.overtime_cap_hours_per_day",
    "attendance.late_grace_minutes",
    "attendance.early_checkout_grace_minutes",
    "attendance.break_tracking_enabled",
    "attendance.auto_break_deduction_minutes",
    "attendance.break_max_minutes_per_day",
)


def snapshot_settings(settings: SettingsView) -> dict[str, Any]:
    from app.modules.settings.service import json_safe

    return {key: json_safe(settings.get(key)) for key in SNAPSHOT_KEYS}

async def lock_employee(session: AsyncSession, employee_id: uuid.UUID) -> None:
    """Transaction-scoped advisory lock serialising attendance events per employee."""
    await session.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"attendance:{employee_id}"},
    )


async def find_open_session(
    session: AsyncSession, employee_id: uuid.UUID
) -> AttendanceSession | None:
    return (
        await session.execute(
            select(AttendanceSession)
            .where(
                AttendanceSession.employee_id == employee_id,
                AttendanceSession.is_open.is_(True),
            )
            .order_by(AttendanceSession.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def find_open_break(session: AsyncSession, record_id: uuid.UUID) -> BreakSession | None:
    return (
        await session.execute(
            select(BreakSession)
            .where(BreakSession.attendance_record_id == record_id, BreakSession.is_open.is_(True))
            .order_by(BreakSession.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def resolve_verification_mode(settings: SettingsView, *, is_checkout: bool) -> str:
    if not is_checkout:
        return settings.str_("attendance.verification_mode")
    mode = settings.str_("attendance.checkout_verification_mode")
    if mode == "SAME_AS_CHECKIN":
        return settings.str_("attendance.verification_mode")
    if mode == "NONE":
        return "NONE"
    return mode


@dataclass(slots=True)
class VerificationBundle:
    overall_method: str
    overall_result: str
    failure_code: str | None
    failure_reason: str | None
    outcomes: list[VerificationOutcome]

    def to_payload(self) -> dict[str, Any]:
        primary = self.outcomes[0] if self.outcomes else None
        return {
            "method": self.overall_method,
            "result": self.overall_result,
            "distance_meters": str(primary.distance_meters) if primary and primary.distance_meters is not None else None,
            "accuracy_meters": str(primary.accuracy_meters) if primary and primary.accuracy_meters is not None else None,
            "geofence_radius_meters": str(primary.geofence_radius_meters)
            if primary and primary.geofence_radius_meters is not None
            else None,
            "qr_result": next((o.qr_result for o in self.outcomes if o.qr_result), None),
            "failure_code": self.failure_code,
            "failure_reason": self.failure_reason,
        }


async def run_verification(
    session: AsyncSession,
    settings: SettingsView,
    *,
    employee_id: uuid.UUID,
    mode: str,
    gps: GpsEvidence,
    qr_payload: str | None,
    qr_purpose: str,
    now: datetime,
) -> VerificationBundle:
    if mode == "NONE":
        return VerificationBundle("NONE", "PASSED", None, None, [])

    parts = GPS_METHODS.get(mode)
    if parts is None:
        raise RuleViolation(f"Unsupported attendance verification mode: {mode}")
    outcomes: list[VerificationOutcome] = []
    if "GPS" in parts:
        outcomes.append(evaluate_gps(settings, gps, now=now))
    if "QR" in parts:
        outcomes.append(
            await consume_qr_token(
                session,
                settings,
                qr_payload=qr_payload or "",
                purpose=qr_purpose,
                employee_id=employee_id,
            )
        )

    required_all = mode in {"GPS_AND_QR", "GPS_ONLY", "QR_ONLY"}
    if mode == "GPS_OR_QR":
        passed = [o for o in outcomes if o.passed]
        failed = [o for o in outcomes if not o.passed]
        if passed:
            overall_result = "PASSED_WITH_WARNING" if failed else "PASSED"
            failure_code = failed[0].failure_code if failed else None
            failure_reason = failed[0].failure_reason if failed else None
            return VerificationBundle(
                mode, overall_result, failure_code, failure_reason, outcomes
            )
        first = failed[0]
        return VerificationBundle(mode, "FAILED", first.failure_code, first.failure_reason, outcomes)

    failures = [o for o in outcomes if not o.passed]
    if failures:
        first = failures[0]
        return VerificationBundle(mode, "FAILED", first.failure_code, first.failure_reason, outcomes)
    return VerificationBundle(mode, "PASSED", None, None, outcomes)


async def persist_verifications(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    event_id: uuid.UUID | None,
    outcomes: list[VerificationOutcome],
    gps: GpsEvidence,
) -> None:
    if not outcomes:
        session.add(
            AttendanceVerification(
                attendance_event_id=event_id,
                employee_id=employee_id,
                method="NONE",
                result="PASSED",
            )
        )
        await session.flush()
        return
    for outcome in outcomes:
        session.add(
            AttendanceVerification(
                attendance_event_id=event_id,
                employee_id=employee_id,
                method=outcome.method,
                result=outcome.result,
                latitude=_dec(gps.latitude, "0.000001"),
                longitude=_dec(gps.longitude, "0.000001"),
                accuracy_meters=_dec(gps.accuracy_meters, "0.01"),
                distance_meters=outcome.distance_meters,
                geofence_radius_meters=outcome.geofence_radius_meters,
                location_captured_at=gps.location_captured_at,
                qr_token_id=outcome.qr_token_id,
                qr_result=outcome.qr_result,
                failure_code=outcome.failure_code,
                failure_reason=outcome.failure_reason,
            )
        )
    await session.flush()

def next_allowed_action(record: AttendanceRecord, has_open_break: bool, has_session: bool) -> str:
    if record.status == "NOT_MARKED":
        return "CHECK_IN"
    if has_open_break:
        return "BREAK_END"
    if has_session:
        return "BREAK_START"
    if not record.is_open:
        return "CHECK_IN"
    return "CHECK_OUT"


def serialize_record(record: AttendanceRecord, *, has_open_break: bool = False, has_session: bool = False) -> dict[str, Any]:
    return {
        "id": record.id,
        "employee_id": record.employee_id,
        "business_date": record.business_date,
        "status": record.status,
        "day_classification": record.day_classification,
        "first_check_in_at": record.first_check_in_at,
        "last_check_out_at": record.last_check_out_at,
        "worked_seconds": record.worked_seconds,
        "worked_hours": hours_str(record.worked_seconds),
        "break_seconds": record.break_seconds,
        "unpaid_break_seconds": record.unpaid_break_seconds,
        "overtime_seconds": record.overtime_seconds,
        "late_minutes": record.late_minutes,
        "early_checkout_minutes": record.early_checkout_minutes,
        "is_open": record.is_open,
        "is_corrected": record.is_corrected,
        "computed_at": record.computed_at,
        "version": record.version,
        "next_allowed_action": next_allowed_action(record, has_open_break, has_session),
    }


def serialize_session(row: AttendanceSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "attendance_record_id": row.attendance_record_id,
        "employee_id": row.employee_id,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_seconds": row.duration_seconds,
        "is_open": row.is_open,
        "start_source": row.start_source,
        "end_source": row.end_source,
        "close_reason": row.close_reason,
    }


def serialize_break(row: BreakSession, break_type: BreakType | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "attendance_record_id": row.attendance_record_id,
        "attendance_session_id": row.attendance_session_id,
        "employee_id": row.employee_id,
        "break_type_id": row.break_type_id,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_seconds": row.duration_seconds,
        "is_paid": row.is_paid,
        "is_open": row.is_open,
        "close_reason": row.close_reason,
        "exceeded_max_minutes": False,
    }
    if break_type is not None:
        payload["break_type"] = serialize_break_type(break_type)
        if (
            break_type.max_minutes is not None
            and row.ended_at is not None
            and (row.ended_at - row.started_at).total_seconds() > break_type.max_minutes * 60
        ):
            payload["exceeded_max_minutes"] = True
    return payload


def serialize_break_type(row: BreakType) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "is_paid": row.is_paid,
        "max_minutes": row.max_minutes,
        "requires_approval": row.requires_approval,
        "counts_toward_max_per_day": row.counts_toward_max_per_day,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
    }


async def _raise_verification_failure(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    bundle: VerificationBundle,
    gps: GpsEvidence,
) -> None:
    """Record failed evidence, persist it, and signal a rule violation."""
    await persist_verifications(
        session, employee_id=employee_id, event_id=None, outcomes=bundle.outcomes, gps=gps
    )
    await session.commit()
    raise RuleViolation(
        bundle.failure_reason or "Attendance verification failed.",
        rule_code="ATTENDANCE_VERIFICATION_FAILED",
        extra={"failure_code": bundle.failure_code, "verification": bundle.to_payload()},
    )


async def check_in(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    gps: GpsEvidence,
    qr_payload: str | None,
    source: str = "WEB",
    actor_user_id: uuid.UUID | None = None,
    meta: Any = None,
) -> tuple[AttendanceRecord, dict[str, Any]]:
    await lock_employee(session, employee.id)
    existing = await find_open_session(session, employee.id)
    now = utcnow()
    if existing is not None:
        record = await get_record_by_id(session, existing.attendance_record_id)
        raise Conflict(
            "You already have an open attendance session.",
            extra={"session": serialize_session(existing), "attendance_record": serialize_record(record)},
        )
    business_date = business_date_of(now, settings.timezone())
    record = await get_or_create_record(session, employee.id, business_date)
    open_break = await find_open_break(session, record.id)
    if open_break is not None:
        raise Conflict("You have an open break that must be ended first.")
    session_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(AttendanceSession)
                .where(AttendanceSession.attendance_record_id == record.id)
            )
        ).scalar_one()
    )
    if session_count >= settings.int_("attendance.max_sessions_per_day"):
        raise RuleViolation(
            "The maximum number of sessions for this day has been reached.",
            rule_code="MAX_SESSIONS_EXCEEDED",
        )

    mode = resolve_verification_mode(settings, is_checkout=False)
    bundle = await run_verification(
        session,
        settings,
        employee_id=employee.id,
        mode=mode,
        gps=gps,
        qr_payload=qr_payload,
        qr_purpose="SHOP_CHECKIN",
        now=now,
    )
    if not bundle.overall_result.startswith("PASSED"):
        await _raise_verification_failure(session, employee_id=employee.id, bundle=bundle, gps=gps)

    event = AttendanceEvent(
        attendance_record_id=record.id,
        employee_id=employee.id,
        event_type="CHECK_IN",
        occurred_at=now,
        business_date=business_date,
        source=source,
        actor_user_id=actor_user_id,
    )
    session.add(event)
    await session.flush()
    session_row = AttendanceSession(
        attendance_record_id=record.id,
        employee_id=employee.id,
        started_at=now,
        started_event_id=event.id,
        start_source=source,
        is_open=True,
    )
    session.add(session_row)
    await session.flush()
    event.attendance_session_id = session_row.id
    payload = {"method": bundle.overall_method, "result": bundle.overall_result}
    await persist_verifications(
        session, employee_id=employee.id, event_id=event.id, outcomes=bundle.outcomes, gps=gps
    )
    for outcome in bundle.outcomes:
        if outcome.qr_token_id is not None:
            await session.execute(
                update(AttendanceQrToken)
                .where(AttendanceQrToken.id == outcome.qr_token_id)
                .values(consumed_event_id=event.id)
            )
    await recompute_record(session, record, settings, reason="CHECK_IN")
    await session.flush()
    return record, {**payload, **bundle.to_payload(), "attendance_session_id": session_row.id}


async def check_out(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    gps: GpsEvidence,
    qr_payload: str | None,
    source: str = "WEB",
    actor_user_id: uuid.UUID | None = None,
    meta: Any = None,
) -> tuple[AttendanceRecord, dict[str, Any]]:
    await lock_employee(session, employee.id)
    open_session = await find_open_session(session, employee.id)
    if open_session is None:
        raise Conflict("You do not have an open attendance session.")
    record = await get_record_by_id(session, open_session.attendance_record_id)
    now = utcnow()
    mode = resolve_verification_mode(settings, is_checkout=True)
    if mode != "NONE":
        bundle = await run_verification(
            session,
            settings,
            employee_id=employee.id,
            mode=mode,
            gps=gps,
            qr_payload=qr_payload,
            qr_purpose="SHOP_CHECKOUT",
            now=now,
        )
        if not bundle.overall_result.startswith("PASSED"):
            await _raise_verification_failure(session, employee_id=employee.id, bundle=bundle, gps=gps)
    else:
        bundle = VerificationBundle("NONE", "PASSED", None, None, [])

    open_break = await find_open_break(session, record.id)
    if open_break is not None:
        raise Conflict("You must end your active break before checking out.")

    event = AttendanceEvent(
        attendance_record_id=record.id,
        employee_id=employee.id,
        event_type="CHECK_OUT",
        occurred_at=now,
        business_date=record.business_date,
        source=source,
        actor_user_id=actor_user_id,
        attendance_session_id=open_session.id,
    )
    session.add(event)
    await session.flush()
    open_session.ended_at = now
    open_session.ended_event_id = event.id
    open_session.end_source = source
    open_session.close_reason = "MANUAL"
    open_session.duration_seconds = int((now - open_session.started_at).total_seconds())
    open_session.is_open = False
    await session.flush()
    await persist_verifications(
        session, employee_id=employee.id, event_id=event.id, outcomes=bundle.outcomes, gps=gps
    )
    await recompute_record(session, record, settings, reason="CHECK_OUT")
    await session.flush()
    return record, {**bundle.to_payload(), "attendance_session_id": open_session.id}

async def break_start(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    break_type_id: uuid.UUID,
    source: str = "WEB",
    actor_user_id: uuid.UUID | None = None,
) -> tuple[BreakSession, BreakType, AttendanceRecord]:
    await lock_employee(session, employee.id)
    open_session = await find_open_session(session, employee.id)
    if open_session is None:
        raise RuleViolation(
            "You must be checked in before starting a break.",
            rule_code="BREAK_WITHOUT_SESSION",
        )
    record = await get_record_by_id(session, open_session.attendance_record_id)
    existing = await find_open_break(session, record.id)
    if existing is not None:
        break_type = await session.get(BreakType, existing.break_type_id)
        raise Conflict(
            "You already have an open break.",
            extra={"break_session": serialize_break(existing, break_type)},
        )
    break_type = await session.get(BreakType, break_type_id)
    if break_type is None or not break_type.is_active:
        raise NotFound("Break type not found.")
    now = utcnow()
    if break_type.counts_toward_max_per_day:
        max_minutes = settings.int_("attendance.break_max_minutes_per_day")
        if max_minutes > 0:
            used = (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                func.coalesce(BreakSession.duration_seconds, 0)
                            ),
                            0,
                        )
                    ).where(
                        BreakSession.attendance_record_id == record.id,
                        BreakSession.break_type_id.in_(
                            select(BreakType.id).where(BreakType.counts_toward_max_per_day.is_(True))
                        ),
                    )
                )
            ).scalar_one()
            if int(used) >= max_minutes * 60:
                raise RuleViolation(
                    "The maximum break time for today has already been used.",
                    rule_code="BREAK_MAX_EXCEEDED",
                )
    event = AttendanceEvent(
        attendance_record_id=record.id,
        employee_id=employee.id,
        event_type="BREAK_START",
        occurred_at=now,
        business_date=record.business_date,
        source=source,
        actor_user_id=actor_user_id,
        break_type_id=break_type.id,
        attendance_session_id=open_session.id,
    )
    session.add(event)
    await session.flush()
    row = BreakSession(
        attendance_record_id=record.id,
        attendance_session_id=open_session.id,
        employee_id=employee.id,
        break_type_id=break_type.id,
        started_at=now,
        start_event_id=event.id,
        is_paid=break_type.is_paid,
        is_open=True,
    )
    session.add(row)
    await session.flush()
    record.is_open = True
    await session.flush()
    return row, break_type, record


async def break_end(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    source: str = "WEB",
    actor_user_id: uuid.UUID | None = None,
) -> tuple[BreakSession, BreakType, AttendanceRecord]:
    await lock_employee(session, employee.id)
    open_session = await find_open_session(session, employee.id)
    if open_session is None:
        raise RuleViolation(
            "You must be checked in to be on a break.", rule_code="BREAK_WITHOUT_SESSION"
        )
    record = await get_record_by_id(session, open_session.attendance_record_id)
    row = await find_open_break(session, record.id)
    if row is None:
        raise Conflict("You do not have an open break.")
    break_type = await session.get(BreakType, row.break_type_id)
    now = utcnow()
    event = AttendanceEvent(
        attendance_record_id=record.id,
        employee_id=employee.id,
        event_type="BREAK_END",
        occurred_at=now,
        business_date=record.business_date,
        source=source,
        actor_user_id=actor_user_id,
        break_type_id=row.break_type_id,
        attendance_session_id=open_session.id,
    )
    session.add(event)
    await session.flush()
    row.ended_at = now
    row.end_event_id = event.id
    row.duration_seconds = int((now - row.started_at).total_seconds())
    row.is_open = False
    row.close_reason = "MANUAL"
    await session.flush()
    await recompute_record(session, record, settings, reason="BREAK_END")
    return row, break_type, record


# ---------------------------------------------------------------------------
# QR tokens
# ---------------------------------------------------------------------------


async def issue_qr_token(
    session: AsyncSession,
    settings: SettingsView,
    *,
    purpose: str,
    issued_by: uuid.UUID,
) -> AttendanceQrToken:
    from app.core.security import new_opaque_token, sha256_hex

    nonce = uuid.uuid4().hex
    secret = new_opaque_token()
    payload = f"wcrm:{purpose}:{nonce}:{secret}"
    now = utcnow()
    row = AttendanceQrToken(
        token_hash=sha256_hex(payload),
        nonce=nonce,
        purpose=purpose,
        issued_by=issued_by,
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.int_("attendance.qr_validity_seconds")),
    )
    session.add(row)
    await session.execute(
        update(AttendanceQrToken)
        .where(AttendanceQrToken.purpose == purpose, AttendanceQrToken.is_revoked.is_(False))
        .values(is_revoked=True)
    )
    await session.flush()
    row.qr_payload = payload  # type: ignore[attr-defined]
    return row


async def current_qr_token(
    session: AsyncSession, *, purpose: str
) -> AttendanceQrToken | None:
    return (
        await session.execute(
            select(AttendanceQrToken)
            .where(
                AttendanceQrToken.purpose == purpose,
                AttendanceQrToken.is_revoked.is_(False),
                AttendanceQrToken.expires_at > utcnow(),
            )
            .order_by(AttendanceQrToken.issued_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Break types and holidays
# ---------------------------------------------------------------------------


async def list_break_types(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[BreakType]:
    stmt = select(BreakType).order_by(BreakType.sort_order, BreakType.code)
    if not include_inactive:
        stmt = stmt.where(BreakType.is_active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def list_holidays(session: AsyncSession, year: int) -> list[BusinessHoliday]:
    return list(
        (
            await session.execute(
                select(BusinessHoliday)
                .where(func.date_part("year", BusinessHoliday.holiday_date) == year)
                .order_by(BusinessHoliday.holiday_date)
            )
        ).scalars().all()
    )


def serialize_holiday(row: BusinessHoliday) -> dict[str, Any]:
    return {
        "id": row.id,
        "holiday_date": row.holiday_date,
        "name": row.name,
        "is_paid": row.is_paid,
        "is_working_day": row.is_working_day,
        "notes": row.notes,
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def query_records(
    session: AsyncSession,
    *,
    employee_ids: list[uuid.UUID] | None = None,
    status: str | None = None,
    day_classification: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    department: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[AttendanceRecord], int]:
    conditions = []
    if employee_ids is not None:
        if not employee_ids:
            return [], 0
        conditions.append(AttendanceRecord.employee_id.in_(employee_ids))
    if status:
        conditions.append(AttendanceRecord.status == status)
    if day_classification:
        conditions.append(AttendanceRecord.day_classification == day_classification)
    if from_date:
        conditions.append(AttendanceRecord.business_date >= from_date)
    if to_date:
        conditions.append(AttendanceRecord.business_date <= to_date)
    stmt = select(AttendanceRecord).order_by(
        AttendanceRecord.business_date.desc(), AttendanceRecord.employee_id
    )
    count_stmt = select(func.count()).select_from(AttendanceRecord)
    if department or q:
        from app.modules.directory.models import Employee as EmployeeModel

        stmt = stmt.join(EmployeeModel, EmployeeModel.id == AttendanceRecord.employee_id)
        count_stmt = count_stmt.join(EmployeeModel, EmployeeModel.id == AttendanceRecord.employee_id)
        if department:
            conditions.append(EmployeeModel.department == department)
        if q:
            pattern = f"%{q.lower()}%"
            conditions.append(
                or_(
                    func.lower(EmployeeModel.full_name).like(pattern),
                    func.lower(EmployeeModel.employee_code).like(pattern),
                )
            )
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def attendance_summary(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == employee_id,
                    AttendanceRecord.business_date >= from_date,
                    AttendanceRecord.business_date <= to_date,
                )
            )
        ).scalars().all()
    )
    totals = {
        "present_days": 0,
        "half_days": 0,
        "partial_days": 0,
        "absent_days": 0,
        "leave_days": 0,
        "holiday_days": 0,
        "weekly_off_days": 0,
        "worked_seconds": 0,
        "break_seconds": 0,
        "overtime_seconds": 0,
        "late_minutes": 0,
        "early_checkout_minutes": 0,
    }
    for row in rows:
        if row.status == "PRESENT":
            totals["present_days"] += 1
        elif row.status == "ABSENT":
            totals["absent_days"] += 1
        elif row.status == "ON_LEAVE":
            totals["leave_days"] += 1
        elif row.status == "HOLIDAY":
            totals["holiday_days"] += 1
        elif row.status == "WEEKLY_OFF":
            totals["weekly_off_days"] += 1
        if row.day_classification == "HALF_DAY":
            totals["half_days"] += 1
        elif row.day_classification == "PARTIAL_DAY":
            totals["partial_days"] += 1
        totals["worked_seconds"] += row.worked_seconds
        totals["break_seconds"] += row.break_seconds
        totals["overtime_seconds"] += row.overtime_seconds
        totals["late_minutes"] += row.late_minutes
        totals["early_checkout_minutes"] += row.early_checkout_minutes
    totals["worked_hours"] = hours_str(totals["worked_seconds"])
    totals["from"] = from_date
    totals["to"] = to_date
    return totals

# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


async def period_locked_for(session: AsyncSession, business_date: date) -> bool:
    """Read-only payroll lock check (deferred import avoids a module cycle)."""
    from app.modules.payroll import service as payroll_service

    return await payroll_service.is_period_locked(session, business_date)


async def request_correction(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    attendance_record_id: uuid.UUID,
    correction_type: str,
    reason: str,
    requested_check_in_at: datetime | None,
    requested_check_out_at: datetime | None,
    requested_break_start_at: datetime | None,
    requested_break_end_at: datetime | None,
    requested_notes: str | None,
    attachment_file_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
) -> AttendanceCorrection:
    record = await get_record_by_id(session, attendance_record_id)
    if record.employee_id != employee.id:
        raise NotFound("Attendance record not found.")
    backdate_limit = settings.int_("attendance.correction_max_backdate_days")
    age_days = (business_date_of(utcnow(), settings.timezone()) - record.business_date).days
    if age_days > backdate_limit:
        from app.core.errors import PeriodLocked

        raise RuleViolation(
            f"Corrections are only allowed for the last {backdate_limit} days.",
            rule_code="CORRECTION_BACKDATE_EXCEEDED",
        )
    if await period_locked_for(session, record.business_date):
        from app.core.errors import PeriodLocked

        raise PeriodLocked("This date belongs to a locked payroll period.")
    pending = (
        await session.execute(
            select(AttendanceCorrection.id).where(
                AttendanceCorrection.attendance_record_id == record.id,
                AttendanceCorrection.status == "PENDING",
            )
        )
    ).scalar_one_or_none()
    if pending:
        raise RuleViolation(
            "A pending correction already exists for this record.", rule_code="CORRECTION_PENDING"
        )
    row = AttendanceCorrection(
        attendance_record_id=record.id,
        employee_id=employee.id,
        correction_type=correction_type,
        requested_by=actor_user_id,
        requested_check_in_at=requested_check_in_at,
        requested_check_out_at=requested_check_out_at,
        requested_break_start_at=requested_break_start_at,
        requested_break_end_at=requested_break_end_at,
        requested_notes=requested_notes,
        reason=reason,
        attachment_file_id=attachment_file_id,
        status="PENDING",
    )
    session.add(row)
    await session.flush()
    if not settings.bool_("attendance.correction_requires_approval"):
        await apply_correction(session, row, settings, actor_user_id=actor_user_id, auto=True)
    return row


async def apply_correction(
    session: AsyncSession,
    correction: AttendanceCorrection,
    settings: SettingsView,
    *,
    actor_user_id: uuid.UUID,
    auto: bool = False,
) -> AttendanceRecord:
    record = await get_record_by_id(session, correction.attendance_record_id)
    correction.previous_computation = {
        "worked_seconds": record.worked_seconds,
        "status": record.status,
        "day_classification": record.day_classification,
        "computation_version": record.computation_version,
    }
    check_in_at = correction.requested_check_in_at
    check_out_at = correction.requested_check_out_at
    if check_in_at is not None or check_out_at is not None:
        sessions = list(
            (
                await session.execute(
                    select(AttendanceSession)
                    .where(AttendanceSession.attendance_record_id == record.id)
                    .order_by(AttendanceSession.started_at)
                )
            ).scalars().all()
        )
        open_session = next((row for row in sessions if row.is_open), None)
        if check_in_at is not None and check_out_at is not None:
            event_in = AttendanceEvent(
                attendance_record_id=record.id,
                employee_id=record.employee_id,
                event_type="CORRECTION",
                occurred_at=check_in_at,
                business_date=record.business_date,
                source="ADMIN",
                actor_user_id=actor_user_id,
                correction_id=correction.id,
                notes=correction.reason,
            )
            event_out = AttendanceEvent(
                attendance_record_id=record.id,
                employee_id=record.employee_id,
                event_type="CORRECTION",
                occurred_at=check_out_at,
                business_date=record.business_date,
                source="ADMIN",
                actor_user_id=actor_user_id,
                correction_id=correction.id,
                notes=correction.reason,
            )
            session.add_all([event_in, event_out])
            await session.flush()
            new_session = AttendanceSession(
                attendance_record_id=record.id,
                employee_id=record.employee_id,
                started_at=check_in_at,
                started_event_id=event_in.id,
                ended_at=check_out_at,
                ended_event_id=event_out.id,
                start_source="ADMIN",
                end_source="ADMIN",
                close_reason="CORRECTION",
                duration_seconds=int((check_out_at - check_in_at).total_seconds()),
                is_open=False,
            )
            session.add(new_session)
            await session.flush()
            correction.applied_event_id = event_out.id
        elif check_out_at is not None and open_session is not None:
            event_out = AttendanceEvent(
                attendance_record_id=record.id,
                employee_id=record.employee_id,
                event_type="CORRECTION",
                occurred_at=check_out_at,
                business_date=record.business_date,
                source="ADMIN",
                actor_user_id=actor_user_id,
                correction_id=correction.id,
                attendance_session_id=open_session.id,
                notes=correction.reason,
            )
            session.add(event_out)
            await session.flush()
            open_session.ended_at = check_out_at
            open_session.ended_event_id = event_out.id
            open_session.end_source = "ADMIN"
            open_session.close_reason = "CORRECTION"
            open_session.duration_seconds = int(
                (check_out_at - open_session.started_at).total_seconds()
            )
            open_session.is_open = False
            correction.applied_event_id = event_out.id
        elif check_in_at is not None:
            existing = next(
                (row for row in sessions if abs((row.started_at - check_in_at).total_seconds()) < 1),
                None,
            )
            if existing is None:
                event_in = AttendanceEvent(
                    attendance_record_id=record.id,
                    employee_id=record.employee_id,
                    event_type="CORRECTION",
                    occurred_at=check_in_at,
                    business_date=record.business_date,
                    source="ADMIN",
                    actor_user_id=actor_user_id,
                    correction_id=correction.id,
                    notes=correction.reason,
                )
                session.add(event_in)
                await session.flush()
                new_session = AttendanceSession(
                    attendance_record_id=record.id,
                    employee_id=record.employee_id,
                    started_at=check_in_at,
                    started_event_id=event_in.id,
                    start_source="ADMIN",
                    is_open=True,
                )
                session.add(new_session)
                await session.flush()
                correction.applied_event_id = event_in.id
    if (
        correction.requested_break_start_at is not None
        and correction.requested_break_end_at is not None
    ):
        default_type = (
            await session.execute(
                select(BreakType).where(BreakType.is_active.is_(True)).order_by(BreakType.sort_order).limit(1)
            )
        ).scalar_one_or_none()
        if default_type is not None:
            event = AttendanceEvent(
                attendance_record_id=record.id,
                employee_id=record.employee_id,
                event_type="CORRECTION",
                occurred_at=correction.requested_break_start_at,
                business_date=record.business_date,
                source="ADMIN",
                actor_user_id=actor_user_id,
                correction_id=correction.id,
                break_type_id=default_type.id,
                notes=correction.reason,
            )
            session.add(event)
            await session.flush()
            break_row = BreakSession(
                attendance_record_id=record.id,
                attendance_session_id=None,
                employee_id=record.employee_id,
                break_type_id=default_type.id,
                started_at=correction.requested_break_start_at,
                start_event_id=event.id,
                ended_at=correction.requested_break_end_at,
                end_event_id=event.id,
                duration_seconds=int(
                    (correction.requested_break_end_at - correction.requested_break_start_at).total_seconds()
                ),
                is_paid=default_type.is_paid,
                is_open=False,
                close_reason="CORRECTION",
            )
            session.add(break_row)
            await session.flush()
    record.is_corrected = True
    correction.status = "APPROVED"
    correction.decided_by = actor_user_id
    correction.decided_at = utcnow()
    await session.flush()
    await recompute_record(session, record, settings, reason="CORRECTION")
    await session.flush()
    return record


async def auto_close_sessions(
    session: AsyncSession, settings: SettingsView
) -> int:
    """Job: close stale open sessions per attendance.missing_checkout_policy."""
    tz = settings.timezone()
    now = utcnow()
    open_rows = list(
        (
            await session.execute(
                select(AttendanceSession).where(AttendanceSession.is_open.is_(True))
            )
        ).scalars().all()
    )
    policy = settings.str_("attendance.missing_checkout_policy")
    handled = 0
    for row in open_rows:
        record = await get_record_by_id(session, row.attendance_record_id)
        _, shift_end = shift_bounds(
            record.business_date,
            settings.time_("attendance.shift_start_time"),
            settings.time_("attendance.shift_end_time"),
            tz,
            settings.bool_("attendance.shift_crosses_midnight"),
        )
        grace = timedelta(minutes=settings.int_("attendance.auto_close_grace_minutes"))
        if now < shift_end + grace:
            continue
        if policy in {"AUTO_CLOSE_AT_SHIFT_END", "AUTO_CLOSE_WITH_MAX", "MARK_INCOMPLETE"}:
            close_at = shift_end
            if policy == "AUTO_CLOSE_WITH_MAX":
                max_seconds = int(settings.decimal_("attendance.auto_close_max_hours") * 3600)
                if (close_at - row.started_at).total_seconds() > max_seconds:
                    close_at = row.started_at + timedelta(seconds=max_seconds)
            event = AttendanceEvent(
                attendance_record_id=record.id,
                employee_id=row.employee_id,
                event_type="AUTO_CLOSE",
                occurred_at=close_at,
                business_date=record.business_date,
                source="SYSTEM",
                attendance_session_id=row.id,
                notes=f"Auto-closed per policy {policy}.",
            )
            session.add(event)
            await session.flush()
            row.ended_at = close_at
            row.ended_event_id = event.id
            row.end_source = "SYSTEM"
            row.close_reason = "AUTO_CLOSE"
            row.duration_seconds = int((close_at - row.started_at).total_seconds())
            row.is_open = False
            open_break = await find_open_break(session, record.id)
            if open_break is not None:
                open_break.ended_at = close_at
                open_break.end_event_id = event.id
                open_break.duration_seconds = int((close_at - open_break.started_at).total_seconds())
                open_break.is_open = False
                open_break.close_reason = "AUTO_CLOSE"
            await session.flush()
            await recompute_record(session, record, settings, reason="AUTO_CLOSE")
            if policy == "MARK_INCOMPLETE":
                record.status = "INCOMPLETE"
                await session.flush()
            handled += 1
    return handled


async def initialize_day(
    session: AsyncSession,
    settings: SettingsView,
    *,
    employee_id: uuid.UUID,
    business_date: date,
) -> AttendanceRecord:
    """Set ON_LEAVE / HOLIDAY / WEEKLY_OFF / ABSENT for a business date (idempotent)."""
    record = await get_or_create_record(session, employee_id, business_date)
    if record.status in {"PRESENT", "INCOMPLETE"} and record.first_check_in_at is not None:
        return record
    holiday = (
        await session.execute(
            select(BusinessHoliday).where(BusinessHoliday.holiday_date == business_date)
        )
    ).scalar_one_or_none()
    if holiday is not None and not holiday.is_working_day:
        new_status = "HOLIDAY"
    else:
        from app.modules.leaves import service as leave_service

        if await leave_service.has_approved_leave(session, employee_id, business_date):
            new_status = "ON_LEAVE"
        elif business_date.weekday() in [
            int(day) for day in settings.json_("payroll.weekly_off_days") or []
        ]:
            new_status = "WEEKLY_OFF"
        else:
            return record
    if record.status != new_status:
        record.status = new_status
        record.day_classification = "NONE"
        record.updated_at = utcnow()
        await session.flush()
    return record

def serialize_correction(row: AttendanceCorrection) -> dict[str, Any]:
    return {
        "id": row.id,
        "attendance_record_id": row.attendance_record_id,
        "employee_id": row.employee_id,
        "correction_type": row.correction_type,
        "requested_by": row.requested_by,
        "requested_at": row.requested_at,
        "requested_check_in_at": row.requested_check_in_at,
        "requested_check_out_at": row.requested_check_out_at,
        "requested_break_start_at": row.requested_break_start_at,
        "requested_break_end_at": row.requested_break_end_at,
        "requested_notes": row.requested_notes,
        "reason": row.reason,
        "attachment_file_id": row.attachment_file_id,
        "status": row.status,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "decision_notes": row.decision_notes,
        "version": row.version,
        "created_at": row.created_at,
    }


async def query_corrections(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    employee_ids: list[uuid.UUID] | None = None,
    status: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[AttendanceCorrection], int]:
    conditions = []
    if employee_id is not None:
        conditions.append(AttendanceCorrection.employee_id == employee_id)
    if employee_ids is not None:
        if not employee_ids:
            return [], 0
        conditions.append(AttendanceCorrection.employee_id.in_(employee_ids))
    if status:
        conditions.append(AttendanceCorrection.status == status)
    stmt = select(AttendanceCorrection).order_by(AttendanceCorrection.requested_at.desc())
    count_stmt = select(func.count()).select_from(AttendanceCorrection)
    if from_date or to_date:
        sub = select(AttendanceRecord.id)
        if from_date:
            sub = sub.where(AttendanceRecord.business_date >= from_date)
        if to_date:
            sub = sub.where(AttendanceRecord.business_date <= to_date)
        conditions.append(AttendanceCorrection.attendance_record_id.in_(sub))
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def get_correction(session: AsyncSession, correction_id: uuid.UUID) -> AttendanceCorrection:
    row = await session.get(AttendanceCorrection, correction_id)
    if row is None:
        raise NotFound("Correction not found.")
    return row


async def record_manual_event(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    event_type: str,
    occurred_at: datetime,
    business_date: date,
    reason: str,
    actor_user_id: uuid.UUID,
) -> AttendanceRecord:
    """Admin manual override (docs/04_BUSINESS_RULES.md BR-4.1)."""
    record = await get_or_create_record(session, employee.id, business_date)
    if await period_locked_for(session, business_date):
        from app.core.errors import PeriodLocked

        raise PeriodLocked("This date belongs to a locked payroll period.")
    event = AttendanceEvent(
        attendance_record_id=record.id,
        employee_id=employee.id,
        event_type=event_type if event_type in {"CHECK_IN", "CHECK_OUT"} else "CORRECTION",
        occurred_at=occurred_at,
        business_date=business_date,
        source="ADMIN",
        actor_user_id=actor_user_id,
        notes=reason,
    )
    session.add(event)
    await session.flush()
    if event.event_type == "CHECK_IN":
        new_session = AttendanceSession(
            attendance_record_id=record.id,
            employee_id=employee.id,
            started_at=occurred_at,
            started_event_id=event.id,
            start_source="ADMIN",
            is_open=True,
        )
        session.add(new_session)
        await session.flush()
    elif event.event_type == "CHECK_OUT":
        open_session = await find_open_session(session, employee.id)
        if open_session is None:
            raise RuleViolation("There is no open session to close.", rule_code="NO_OPEN_SESSION")
        open_session.ended_at = occurred_at
        open_session.ended_event_id = event.id
        open_session.end_source = "ADMIN"
        open_session.close_reason = "MANUAL"
        open_session.duration_seconds = int((occurred_at - open_session.started_at).total_seconds())
        open_session.is_open = False
        await session.flush()
    await persist_verifications(
        session,
        employee_id=employee.id,
        event_id=event.id,
        outcomes=[VerificationOutcome(method="MANUAL_OVERRIDE", result="PASSED")],
        gps=GpsEvidence(),
    )
    record.is_corrected = True
    await session.flush()
    await recompute_record(session, record, settings, reason="MANUAL_OVERRIDE")
    await session.flush()
    return record


async def list_events(session: AsyncSession, record_id: uuid.UUID) -> list[AttendanceEvent]:
    return list(
        (
            await session.execute(
                select(AttendanceEvent)
                .where(AttendanceEvent.attendance_record_id == record_id)
                .order_by(AttendanceEvent.occurred_at)
            )
        ).scalars().all()
    )


async def list_verifications(
    session: AsyncSession, record_id: uuid.UUID
) -> list[AttendanceVerification]:
    return list(
        (
            await session.execute(
                select(AttendanceVerification)
                .join(
                    AttendanceEvent,
                    AttendanceEvent.id == AttendanceVerification.attendance_event_id,
                    isouter=True,
                )
                .where(
                    or_(
                        AttendanceEvent.attendance_record_id == record_id,
                        AttendanceVerification.employee_id
                        == select(AttendanceRecord.employee_id)
                        .where(AttendanceRecord.id == record_id)
                        .scalar_subquery(),
                    )
                )
                .order_by(AttendanceVerification.created_at)
            )
        ).scalars().all()
    )


def serialize_event(row: AttendanceEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "attendance_record_id": row.attendance_record_id,
        "employee_id": row.employee_id,
        "event_type": row.event_type,
        "occurred_at": row.occurred_at,
        "recorded_at": row.recorded_at,
        "business_date": row.business_date,
        "source": row.source,
        "actor_user_id": row.actor_user_id,
        "break_type_id": row.break_type_id,
        "attendance_session_id": row.attendance_session_id,
        "correction_id": row.correction_id,
        "notes": row.notes,
    }


def serialize_verification(row: AttendanceVerification) -> dict[str, Any]:
    return {
        "id": row.id,
        "attendance_event_id": row.attendance_event_id,
        "employee_id": row.employee_id,
        "method": row.method,
        "result": row.result,
        "latitude": str(row.latitude) if row.latitude is not None else None,
        "longitude": str(row.longitude) if row.longitude is not None else None,
        "accuracy_meters": str(row.accuracy_meters) if row.accuracy_meters is not None else None,
        "distance_meters": str(row.distance_meters) if row.distance_meters is not None else None,
        "geofence_radius_meters": str(row.geofence_radius_meters)
        if row.geofence_radius_meters is not None
        else None,
        "location_captured_at": row.location_captured_at,
        "qr_token_id": row.qr_token_id,
        "qr_result": row.qr_result,
        "failure_code": row.failure_code,
        "failure_reason": row.failure_reason,
        "created_at": row.created_at,
    }
"""Attendance tables (docs/02_DATABASE.md section 9)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import (
    bool_false,
    bool_true,
    created_at_col,
    uuid_pk,
    version_col,
)

RECORD_STATUS = "('NOT_MARKED','PRESENT','INCOMPLETE','ABSENT','ON_LEAVE','HOLIDAY','WEEKLY_OFF')"
DAY_CLASS = "('FULL_DAY','HALF_DAY','PARTIAL_DAY','NONE')"
EVENT_TYPE = "('CHECK_IN','CHECK_OUT','BREAK_START','BREAK_END','CORRECTION','AUTO_CLOSE')"
SOURCE = "('WEB','MOBILE_WEB','PWA','ADMIN','SYSTEM')"
CLOSE_REASON = "('MANUAL','AUTO_CLOSE','CORRECTION')"
VERIFY_METHOD = "('GPS','QR','GPS_AND_QR','MANUAL_OVERRIDE','NONE')"
VERIFY_RESULT = "('PASSED','FAILED','PASSED_WITH_WARNING')"
QR_RESULT = "('VALID','EXPIRED','REPLAYED','INVALID')"
FAILURE_CODES = (
    "('LOCATION_UNAVAILABLE','LOCATION_STALE','ACCURACY_EXCEEDS_LIMIT','OUTSIDE_GEOFENCE',"
    "'QR_MISSING','QR_EXPIRED','QR_REPLAYED','QR_INVALID','METHOD_NOT_ALLOWED',"
    "'ATTENDANCE_STATE_INVALID','RATE_LIMITED')"
)
CORRECTION_TYPES = (
    "('MISSED_CHECK_IN','MISSED_CHECK_OUT','MISSED_BREAK','WRONG_TIME','WRONG_CLASSIFICATION','OTHER')"
)
CORRECTION_STATUS = "('PENDING','APPROVED','REJECTED','CANCELLED')"
QR_PURPOSE = "('SHOP_CHECKIN','SHOP_CHECKOUT')"


class BreakType(Base):
    __tablename__ = "break_types"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_paid: Mapped[bool] = bool_false()
    max_minutes: Mapped[int | None] = mapped_column(Integer)
    requires_approval: Mapped[bool] = bool_false()
    counts_toward_max_per_day: Mapped[bool] = bool_true()
    is_active: Mapped[bool] = bool_true()
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("max_minutes IS NULL OR max_minutes > 0", name="ck_break_types_max_minutes"),
    )


class BusinessHoliday(Base):
    __tablename__ = "business_holidays"

    id: Mapped[uuid.UUID] = uuid_pk()
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_paid: Mapped[bool] = bool_true()
    is_working_day: Mapped[bool] = bool_false()
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NOT_MARKED'"))
    day_classification: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NONE'"))
    first_check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worked_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    break_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unpaid_break_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    overtime_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    early_checkout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_open: Mapped[bool] = bool_false()
    is_corrected: Mapped[bool] = bool_false()
    computation_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    settings_snapshot: Mapped[Any | None] = mapped_column(JSONB)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("employee_id", "business_date", name="uq_attendance_records_employee_date"),
        CheckConstraint(f"status IN {RECORD_STATUS}", name="ck_attendance_records_status"),
        CheckConstraint(f"day_classification IN {DAY_CLASS}", name="ck_attendance_records_classification"),
        CheckConstraint("worked_seconds >= 0", name="ck_attendance_records_worked"),
        CheckConstraint("break_seconds >= 0", name="ck_attendance_records_break"),
        CheckConstraint("unpaid_break_seconds >= 0", name="ck_attendance_records_unpaid_break"),
        CheckConstraint("overtime_seconds >= 0", name="ck_attendance_records_overtime"),
        CheckConstraint("late_minutes >= 0", name="ck_attendance_records_late"),
        CheckConstraint("early_checkout_minutes >= 0", name="ck_attendance_records_early"),
        Index("ix_attendance_records_business_date", "business_date"),
        Index("ix_attendance_records_status_date", "status", "business_date"),
        Index("ix_attendance_records_open", "employee_id", postgresql_where=text("is_open")),
        Index("ix_attendance_records_employee_date", "employee_id", text("business_date DESC")),
    )


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_records.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    break_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("break_types.id")
    )
    attendance_session_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correction_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"event_type IN {EVENT_TYPE}", name="ck_attendance_events_type"),
        CheckConstraint(f"source IN {SOURCE}", name="ck_attendance_events_source"),
        CheckConstraint(
            "(event_type IN ('BREAK_START','BREAK_END')) = (break_type_id IS NOT NULL)",
            name="ck_attendance_events_break_type",
        ),
        Index("ix_attendance_events_record_occurred", "attendance_record_id", "occurred_at"),
        Index("ix_attendance_events_employee_occurred", "employee_id", text("occurred_at DESC")),
    )


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_records.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_events.id"), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_events.id")
    )
    start_source: Mapped[str] = mapped_column(Text, nullable=False)
    end_source: Mapped[str | None] = mapped_column(Text)
    close_reason: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    is_open: Mapped[bool] = bool_true()

    __table_args__ = (
        CheckConstraint("(ended_at IS NULL) = is_open", name="ck_attendance_sessions_open_flag"),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ck_attendance_sessions_order"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_attendance_sessions_duration"),
        CheckConstraint(f"start_source IN {SOURCE}", name="ck_attendance_sessions_start_source"),
        CheckConstraint(f"end_source IS NULL OR end_source IN {SOURCE}", name="ck_attendance_sessions_end_source"),
        CheckConstraint(f"close_reason IS NULL OR close_reason IN {CLOSE_REASON}", name="ck_attendance_sessions_close_reason"),
        Index("ix_attendance_sessions_record", "attendance_record_id"),
        Index("ix_attendance_sessions_employee_started", "employee_id", text("started_at DESC")),
        Index(
            "uq_attendance_sessions_open_employee",
            "employee_id",
            unique=True,
            postgresql_where=text("is_open"),
        ),
    )


class BreakSession(Base):
    __tablename__ = "break_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_records.id"), nullable=False
    )
    attendance_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_sessions.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    break_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("break_types.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_events.id"), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_events.id")
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    is_paid: Mapped[bool] = bool_false()
    is_open: Mapped[bool] = bool_true()
    close_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("(ended_at IS NULL) = is_open", name="ck_break_sessions_open_flag"),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ck_break_sessions_order"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_break_sessions_duration"),
        CheckConstraint(f"close_reason IS NULL OR close_reason IN {CLOSE_REASON}", name="ck_break_sessions_close_reason"),
        Index("ix_break_sessions_record", "attendance_record_id"),
        Index(
            "uq_break_sessions_open_employee",
            "employee_id",
            unique=True,
            postgresql_where=text("is_open"),
        ),
    )


class AttendanceQrToken(Base):
    __tablename__ = "attendance_qr_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nonce: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SHOP_CHECKIN'"))
    issued_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id")
    )
    consumed_event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    is_revoked: Mapped[bool] = bool_false()

    __table_args__ = (
        CheckConstraint(f"purpose IN {QR_PURPOSE}", name="ck_attendance_qr_tokens_purpose"),
        CheckConstraint("expires_at > issued_at", name="ck_attendance_qr_tokens_expiry"),
        Index("ix_attendance_qr_tokens_expires_at", "expires_at"),
    )


class AttendanceVerification(Base):
    __tablename__ = "attendance_verifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    attendance_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_events.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    accuracy_meters: Mapped[float | None] = mapped_column(Numeric(8, 2))
    distance_meters: Mapped[float | None] = mapped_column(Numeric(10, 2))
    geofence_radius_meters: Mapped[float | None] = mapped_column(Numeric(8, 2))
    location_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qr_token_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_qr_tokens.id")
    )
    qr_result: Mapped[str | None] = mapped_column(Text)
    failure_code: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_metadata: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"method IN {VERIFY_METHOD}", name="ck_attendance_verifications_method"),
        CheckConstraint(f"result IN {VERIFY_RESULT}", name="ck_attendance_verifications_result"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_attendance_verifications_latitude"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_attendance_verifications_longitude"),
        CheckConstraint("accuracy_meters IS NULL OR accuracy_meters >= 0", name="ck_attendance_verifications_accuracy"),
        CheckConstraint("distance_meters IS NULL OR distance_meters >= 0", name="ck_attendance_verifications_distance"),
        CheckConstraint(f"qr_result IS NULL OR qr_result IN {QR_RESULT}", name="ck_attendance_verifications_qr_result"),
        CheckConstraint(f"failure_code IS NULL OR failure_code IN {FAILURE_CODES}", name="ck_attendance_verifications_failure_code"),
        Index("ix_attendance_verifications_event", "attendance_event_id"),
        Index("ix_attendance_verifications_employee_created", "employee_id", text("created_at DESC")),
        Index("ix_attendance_verifications_qr_token", "qr_token_id"),
    )


class AttendanceCorrection(Base):
    __tablename__ = "attendance_corrections"

    id: Mapped[uuid.UUID] = uuid_pk()
    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_records.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    correction_type: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    requested_check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_break_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_break_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_notes: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_file_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    applied_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_events.id")
    )
    previous_computation: Mapped[Any | None] = mapped_column(JSONB)
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(f"correction_type IN {CORRECTION_TYPES}", name="ck_attendance_corrections_type"),
        CheckConstraint(f"status IN {CORRECTION_STATUS}", name="ck_attendance_corrections_status"),
        CheckConstraint(
            "status <> 'APPROVED' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_attendance_corrections_decided",
        ),
        CheckConstraint(
            "requested_check_out_at IS NULL OR requested_check_in_at IS NULL"
            " OR requested_check_out_at > requested_check_in_at",
            name="ck_attendance_corrections_time_order",
        ),
        Index("ix_attendance_corrections_status_requested", "status", "requested_at"),
        Index("ix_attendance_corrections_employee", "employee_id", text("requested_at DESC")),
        Index("ix_attendance_corrections_record", "attendance_record_id"),
    )
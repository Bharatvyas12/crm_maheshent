"""Report export table (docs/02_DATABASE.md section 13.7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import created_at_col, uuid_pk


class ReportExport(Base):
    __tablename__ = "report_exports"

    id: Mapped[uuid.UUID] = uuid_pk()
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'QUEUED'"))
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("files.id"))
    row_count: Mapped[int | None] = mapped_column(Integer)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = created_at_col()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("format IN ('CSV','XLSX','PDF')", name="ck_report_exports_format"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETED','FAILED','EXPIRED')",
            name="ck_report_exports_status",
        ),
        CheckConstraint("row_count IS NULL OR row_count >= 0", name="ck_report_exports_row_count"),
        Index("ix_report_exports_requested_by", "requested_by", text("requested_at DESC")),
        Index("ix_report_exports_status", "status"),
    )
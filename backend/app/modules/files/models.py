"""Files table (docs/02_DATABASE.md section 8.1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import created_at_col, uuid_pk

FILE_PURPOSES = (
    "('TASK_EVIDENCE','TASK_BRIEF','ORDER_PACKING_PROOF','ORDER_DELIVERY_PROOF',"
    "'ORDER_CUSTOMER_CONFIRMATION','LEAVE_ATTACHMENT','COMPLAINT_EVIDENCE',"
    "'ATTENDANCE_CORRECTION','PAYROLL_DOCUMENT','REPORT_EXPORT')"
)
SCAN_STATUSES = "('NOT_SCANNED','CLEAN','INFECTED','FAILED')"


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = uuid_pk()
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    scan_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'NOT_SCANNED'")
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"purpose IS NULL OR purpose IN {FILE_PURPOSES}", name="ck_files_purpose"),
        CheckConstraint(f"scan_status IN {SCAN_STATUSES}", name="ck_files_scan_status"),
        CheckConstraint("size_bytes > 0", name="ck_files_size_positive"),
        Index("ix_files_uploaded_by", "uploaded_by"),
        Index("ix_files_entity", "entity_type", "entity_id"),
        Index("ix_files_checksum", "checksum_sha256"),
    )
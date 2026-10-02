"""Settings tables (docs/02_DATABASE.md section 7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bigint_pk, bool_false, created_at_col, uuid_pk

VALUE_TYPES = "('STRING','INT','DECIMAL','BOOL','JSON','TIME','TIMEZONE','DURATION_SECONDS')"


class BusinessSetting(Base):
    __tablename__ = "business_settings"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_provisional: Mapped[bool] = bool_false()
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"value_type IN {VALUE_TYPES}", name="ck_business_settings_value_type"),
    )


class BusinessSettingHistory(Base):
    __tablename__ = "business_setting_history"

    id: Mapped[int] = bigint_pk()
    setting_key: Mapped[str] = mapped_column(Text, nullable=False)
    setting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_business_setting_history_key_changed_at", "setting_key", text("changed_at DESC")),
    )
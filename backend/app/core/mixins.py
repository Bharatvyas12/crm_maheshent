"""Reusable SQLAlchemy column factories shared by every module's models.

These are factory *functions* (not shared annotations) so each column gets its own
`mapped_column()` instance, which SQLAlchemy requires.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import mapped_column


def uuid_pk() -> Any:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def bigint_pk() -> Any:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


def created_at_col() -> Any:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_col() -> Any:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


def version_col() -> Any:
    return mapped_column(Integer, nullable=False, server_default=text("1"))


def bool_false() -> Any:
    return mapped_column(Boolean, nullable=False, server_default=text("false"))


def bool_true() -> Any:
    return mapped_column(Boolean, nullable=False, server_default=text("true"))


def money_col(*, nullable: bool = False, default: str | None = None) -> Any:
    kwargs: dict[str, Any] = {"nullable": nullable}
    if default is not None:
        kwargs["server_default"] = text(default)
    return mapped_column(Numeric(14, 2), **kwargs)


def rate_col(*, nullable: bool = False) -> Any:
    return mapped_column(Numeric(14, 4), nullable=nullable)


def days_col(*, nullable: bool = False) -> Any:
    return mapped_column(Numeric(6, 2), nullable=nullable)


def tstz(*, nullable: bool = True) -> Any:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def moment_of(value: datetime) -> datetime:
    return value
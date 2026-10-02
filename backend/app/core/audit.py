"""Audit writer contract consumed by modules (implemented by the audit module)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

AUDIT_CATEGORIES = frozenset(
    {
        "AUTH",
        "SECURITY",
        "PERMISSION",
        "EMPLOYEE",
        "SETTINGS",
        "ATTENDANCE",
        "TASK",
        "ORDER",
        "LEAVE",
        "FINANCIAL",
        "COMPLAINT",
        "FILE",
    }
)

REDACTED_KEYS = {
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "token",
    "token_hash",
    "reset_token",
    "csrf_token_hash",
    "secret",
    "bank_account_number",
}


def redact(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        key: ("***REDACTED***" if key.lower() in REDACTED_KEYS else value)
        for key, value in payload.items()
    }


@dataclass(slots=True)
class AuditRecord:
    category: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    actor_type: str = "USER"
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str | None = None
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None

    def sanitized(self) -> "AuditRecord":
        self.before = redact(self.before)
        self.after = redact(self.after)
        return self


class AuditWriter(Protocol):
    def __call__(self, session: Any, record: AuditRecord) -> Any: ...


@dataclass(slots=True)
class RequestMeta:
    """Request-scoped metadata attached to audit records."""

    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
"""Domain event envelope and registry (docs/01_ARCHITECTURE.md section 9).

`core` defines the vocabulary; the `platform` module owns the `domain_events`
table and performs the transactional outbox write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "identity.session.created.v1",
        "identity.login.failed.v1",
        "directory.employee.created.v1",
        "directory.employee.deactivated.v1",
        "settings.changed.v1",
        "attendance.checked_in.v1",
        "attendance.checked_out.v1",
        "attendance.break_started.v1",
        "attendance.break_ended.v1",
        "attendance.corrected.v1",
        "attendance.record_recalculated.v1",
        "task.assigned.v1",
        "task.started.v1",
        "task.submitted.v1",
        "task.approved.v1",
        "task.rejected.v1",
        "task.resubmission_requested.v1",
        "task.cancelled.v1",
        "order.broadcasted.v1",
        "order.claimed.v1",
        "order.claim_released.v1",
        "order.status_changed.v1",
        "order.reassigned.v1",
        "order.cancelled.v1",
        "order.failed.v1",
        "order.delivered.v1",
        "leave.requested.v1",
        "leave.approved.v1",
        "leave.rejected.v1",
        "leave.cancelled.v1",
        "payroll.advance_issued.v1",
        "payroll.advance_repaid.v1",
        "payroll.salary_finalized.v1",
        "payroll.ledger_entry_created.v1",
        "complaint.created.v1",
        "complaint.status_changed.v1",
        "complaint.resolved.v1",
    }
)


@dataclass(slots=True)
class EventEnvelope:
    event_type: str
    aggregate_type: str
    aggregate_id: str | None = None
    actor_user_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
"""Platform services: transactional outbox, idempotency guard, job runs.

`platform` depends only on `core` (docs/01_ARCHITECTURE.md section 7); modules may
import this service, but this service never imports a domain module.
"""

from __future__ import annotations

import hashlib
import json
import socket
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    Conflict,
    DependencyUnavailable,
    IdempotencyConflict,
    ValidationError,
)
from app.core.events import EVENT_TYPES, EventEnvelope
from app.core.timeutil import utcnow
from app.platform.models import DomainEvent, IdempotencyKey, JobRun

# ---------------------------------------------------------------------------
# Transactional outbox
# ---------------------------------------------------------------------------


def emit_event(
    session: AsyncSession,
    event_type: str,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID | str | None = None,
    actor_user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> DomainEvent:
    """Append a domain event to the outbox inside the caller's transaction."""
    if event_type not in EVENT_TYPES:
        raise ValidationError(f"Unknown domain event type: {event_type}")
    row = DomainEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=_as_uuid(aggregate_id),
        actor_user_id=actor_user_id,
        payload=payload or {},
        correlation_id=correlation_id,
        occurred_at=utcnow(),
    )
    session.add(row)
    return row


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


async def fetch_pending_events(session: AsyncSession, limit: int) -> list[DomainEvent]:
    stmt = (
        select(DomainEvent)
        .where(DomainEvent.dispatched_at.is_(None), DomainEvent.next_attempt_at <= utcnow())
        .order_by(DomainEvent.occurred_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.execute(stmt)).scalars().all())


async def mark_events_dispatched(session: AsyncSession, events: list[DomainEvent]) -> None:
    now = utcnow()
    for event in events:
        event.dispatched_at = now
    await session.flush()


async def mark_event_failed(session: AsyncSession, event: DomainEvent, error: str) -> None:
    event.attempts = int(event.attempts or 0) + 1
    event.last_error = error[:1000]
    event.next_attempt_at = utcnow() + timedelta(seconds=min(300, 5 * event.attempts))
    await session.flush()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def request_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class IdempotencyGuard:
    """Database-backed idempotency for unsafe, retryable endpoints.

    The unique constraint `(user_id, endpoint, key)` makes exactly one concurrent
    first-writer win; the loser either replays the stored response or conflicts.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        key: str,
        user_id: uuid.UUID,
        endpoint: str,
        request_hash: str,
        ttl_hours: int = 24,
    ) -> None:
        self.session = session
        self.key = key
        self.user_id = user_id
        self.endpoint = endpoint
        self.request_hash = request_hash
        self.ttl_hours = ttl_hours
        self._claimed = False

    async def begin(self) -> dict[str, Any] | None:
        """Claim the key. Returns a stored response to replay, or None to proceed."""
        existing = (
            await self.session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == self.user_id,
                    IdempotencyKey.endpoint == self.endpoint,
                    IdempotencyKey.key == self.key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self._replay_or_conflict(existing)

        stmt = (
            pg_insert(IdempotencyKey)
            .values(
                id=uuid.uuid4(),
                key=self.key,
                user_id=self.user_id,
                endpoint=self.endpoint,
                request_hash=self.request_hash,
                state="IN_PROGRESS",
                created_at=utcnow(),
                expires_at=utcnow() + timedelta(hours=self.ttl_hours),
            )
            .on_conflict_do_nothing(constraint="uq_idempotency_keys_scope")
            .returning(IdempotencyKey.id)
        )
        inserted = (await self.session.execute(stmt)).scalar_one_or_none()
        if inserted is not None:
            self._claimed = True
            return None
        # Lost the insert race: reload and replay/conflict.
        await self.session.flush()
        existing = (
            await self.session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == self.user_id,
                    IdempotencyKey.endpoint == self.endpoint,
                    IdempotencyKey.key == self.key,
                )
            )
        ).scalar_one()
        return self._replay_or_conflict(existing)

    def _replay_or_conflict(self, row: IdempotencyKey) -> dict[str, Any] | None:
        if row.request_hash != self.request_hash:
            raise IdempotencyConflict(
                "This Idempotency-Key was already used with a different request payload."
            )
        if row.state == "COMPLETED" and row.response_body is not None:
            return {"status": row.response_status, "body": row.response_body}
        raise Conflict(
            "An identical request is already in progress.",
            rule_code="IDEMPOTENCY_IN_PROGRESS",
        )

    async def complete(self, status_code: int, body: dict[str, Any]) -> None:
        if not self._claimed:
            return
        row = (
            await self.session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == self.user_id,
                    IdempotencyKey.endpoint == self.endpoint,
                    IdempotencyKey.key == self.key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.state = "COMPLETED"
        row.response_status = status_code
        row.response_body = json.loads(json.dumps(body, default=str))
        row.completed_at = utcnow()
        await self.session.flush()


# ---------------------------------------------------------------------------
# Job runs
# ---------------------------------------------------------------------------


async def acquire_advisory_lock(session: AsyncSession, name: str) -> bool:
    """Non-blocking advisory lock so only one worker runs a given job."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    result = await session.execute(text("select pg_try_advisory_lock(:k)"), {"k": key})
    return bool(result.scalar())


async def release_advisory_lock(session: AsyncSession, name: str) -> None:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    await session.execute(text("select pg_advisory_unlock(:k)"), {"k": key})


async def start_job_run(session: AsyncSession, job_name: str) -> JobRun:
    run = JobRun(
        job_name=job_name,
        status="RUNNING",
        started_at=utcnow(),
        host=socket.gethostname()[:200],
        items_processed=0,
    )
    session.add(run)
    await session.flush()
    return run


async def finish_job_run(
    session: AsyncSession, run: JobRun, *, status: str, items: int = 0, error: str | None = None
) -> None:
    run.status = status
    run.items_processed = items
    run.last_error = error
    run.finished_at = utcnow()
    await session.flush()


def ensure_dependency(condition: bool, message: str) -> None:
    if not condition:
        raise DependencyUnavailable(message)
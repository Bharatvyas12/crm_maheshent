"""Idempotency-Key handling for unsafe, retryable endpoints (architecture 13.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response

from app.api.context import Ctx
from app.platform.service import IdempotencyGuard, request_fingerprint

IDEMPOTENCY_HEADER = "idempotency-key"
MAX_KEY_LENGTH = 128


@dataclass(slots=True)
class Replay:
    status: int
    body: Any


async def begin_idempotency(
    ctx: Ctx, request: Request, *, endpoint: str, payload: Any
) -> tuple[IdempotencyGuard | None, Replay | None]:
    raw_key = request.headers.get(IDEMPOTENCY_HEADER)
    if not raw_key:
        return None, None
    if len(raw_key) > MAX_KEY_LENGTH:
        from app.core.errors import ValidationError

        raise ValidationError("Idempotency-Key must be at most 128 characters.")
    guard = IdempotencyGuard(
        ctx.session,
        key=raw_key,
        user_id=ctx.actor_user_id,
        endpoint=endpoint,
        request_hash=request_fingerprint(payload),
        ttl_hours=ctx.settings.int_("platform.idempotency_ttl_hours"),
    )
    stored = await guard.begin()
    if stored is not None:
        return None, Replay(status=stored["status"], body=stored["body"])
    return guard, None


async def finish_idempotency(
    guard: IdempotencyGuard | None, status_code: int, body: Any
) -> None:
    if guard is None:
        return
    if isinstance(body, dict):
        await guard.complete(status_code, body)


def replay_response(replay: Replay) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=replay.status,
        content=replay.body,
        headers={"Idempotency-Replayed": "true"},
    )
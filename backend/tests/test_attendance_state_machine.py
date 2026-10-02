"""Priority 2 - attendance state transitions and verification (docs/06_WORKFLOWS.md, BR-4.5).

Covers the full check-in / break / check-out state machine, the GPS + geofence +
accuracy + staleness rules, dynamic QR single-use replay protection, and the
duplicate/illegal-transition guards. All thresholds come from the DB settings
layer; tests read the configured shop coordinates (set in ``conftest``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

SHOP_LAT = "12.971600"
SHOP_LON = "77.594600"
FAR_LAT = "13.100000"  # ~15 km away, outside the 100 m geofence


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence(**over):
    payload = {
        "latitude": SHOP_LAT,
        "longitude": SHOP_LON,
        "accuracy_meters": "8.00",
        "location_captured_at": _now(),
    }
    payload.update(over)
    return payload


async def _qr(admin, purpose: str = "SHOP_CHECKIN") -> str:
    resp = await admin.post("/api/v1/attendance/qr-tokens", json={"purpose": purpose})
    assert resp.status_code == 201, resp.text
    return resp.json()["qr_payload"]


async def check_in(employee_client, admin, **over):
    body = _evidence(**over)
    body.setdefault("qr_token", await _qr(admin, "SHOP_CHECKIN"))
    return await employee_client.post("/api/v1/attendance/check-in", json=body)


async def check_out(employee_client, admin, **over):
    body = _evidence(**over)
    body.setdefault("qr_token", await _qr(admin, "SHOP_CHECKOUT"))
    return await employee_client.post("/api/v1/attendance/check-out", json=body)


@pytest.fixture
async def worker(employee_factory):
    body, client = await employee_factory()
    return body, client


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
async def test_check_in_then_check_out_happy_path(worker, admin):
    _, emp = worker
    r1 = await check_in(emp, admin)
    assert r1.status_code in (200, 201), r1.text
    assert r1.json()["status"] in ("PRESENT", "OPEN", "IN_PROGRESS", "INCOMPLETE")
    r2 = await check_out(emp, admin)
    assert r2.status_code in (200, 201), r2.text


async def test_check_in_records_verifications(worker, admin):
    _, emp = worker
    r = await check_in(emp, admin)
    assert r.status_code in (200, 201), r.text
    record_id = r.json()["id"] if "id" in r.json() else r.json()["attendance_record"]["id"]
    admin_resp = await admin.get(f"/api/v1/attendance/{record_id}/verifications")
    assert admin_resp.status_code == 200
    assert admin_resp.json()["items"]


async def test_today_endpoint_reflects_open_session(worker, admin):
    _, emp = worker
    before = (await emp.get("/api/v1/attendance/me/today")).json()
    await check_in(emp, admin)
    after = (await emp.get("/api/v1/attendance/me/today")).json()
    assert after != before


# --------------------------------------------------------------------------- #
# duplicate / illegal transitions
# --------------------------------------------------------------------------- #
async def test_duplicate_check_in_is_conflict(worker, admin):
    _, emp = worker
    assert (await check_in(emp, admin)).status_code in (200, 201)
    second = await check_in(emp, admin)
    assert second.status_code == 409, second.text
    assert second.json()["code"] in ("STATE_CONFLICT", "CONFLICT_DUPLICATE")


async def test_check_out_without_check_in_is_conflict(worker, admin):
    _, emp = worker
    resp = await check_out(emp, admin)
    assert resp.status_code == 409, resp.text


async def test_break_start_without_open_session_is_conflict(worker):
    _, emp = worker
    break_types = (await emp.get("/api/v1/break-types")).json()["items"]
    resp = await emp.post(
        "/api/v1/attendance/break/start", json={"break_type_id": break_types[0]["id"]}
    )
    assert resp.status_code in (409, 422), resp.text


async def test_break_end_without_open_break_is_conflict(worker, admin):
    _, emp = worker
    assert (await check_in(emp, admin)).status_code in (200, 201)
    resp = await emp.post("/api/v1/attendance/break/end")
    assert resp.status_code == 409, resp.text


async def test_check_out_while_on_break_is_conflict(worker, admin):
    _, emp = worker
    assert (await check_in(emp, admin)).status_code in (200, 201)
    break_types = (await emp.get("/api/v1/break-types")).json()["items"]
    started = await emp.post(
        "/api/v1/attendance/break/start", json={"break_type_id": break_types[0]["id"]}
    )
    assert started.status_code in (200, 201), started.text
    resp = await check_out(emp, admin)
    assert resp.status_code == 409, resp.text


async def test_break_lifecycle_start_and_end(worker, admin):
    _, emp = worker
    assert (await check_in(emp, admin)).status_code in (200, 201)
    break_types = (await emp.get("/api/v1/break-types")).json()["items"]
    started = await emp.post(
        "/api/v1/attendance/break/start", json={"break_type_id": break_types[0]["id"]}
    )
    assert started.status_code in (200, 201), started.text
    ended = await emp.post("/api/v1/attendance/break/end")
    assert ended.status_code in (200, 201), ended.text


# --------------------------------------------------------------------------- #
# verification rules
# --------------------------------------------------------------------------- #
async def test_check_in_without_evidence_fails(worker):
    _, emp = worker
    resp = await emp.post("/api/v1/attendance/check-in", json={})
    assert resp.status_code == 422, resp.text
    assert resp.json()["rule_code"] == "ATTENDANCE_VERIFICATION_FAILED"


async def test_check_in_outside_geofence_fails(worker, admin):
    _, emp = worker
    resp = await check_in(emp, admin, latitude=FAR_LAT, longitude=SHOP_LON)
    assert resp.status_code == 422, resp.text
    detail = resp.json()
    assert detail["rule_code"] == "ATTENDANCE_VERIFICATION_FAILED"
    assert detail.get("failure_code") == "OUTSIDE_GEOFENCE"


async def test_check_in_with_poor_accuracy_fails(worker, admin):
    _, emp = worker
    resp = await check_in(emp, admin, accuracy_meters="5000.00")
    assert resp.status_code == 422, resp.text
    assert resp.json().get("failure_code") in ("ACCURACY_EXCEEDS_LIMIT", "ACCURACY_TOO_LOW")


async def test_check_in_with_stale_location_fails(worker, admin):
    _, emp = worker
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    resp = await check_in(emp, admin, location_captured_at=stale)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("failure_code") == "LOCATION_STALE"


async def test_check_in_without_qr_fails(worker):
    _, emp = worker
    payload = _evidence()
    resp = await emp.post("/api/v1/attendance/check-in", json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("failure_code") in ("QR_MISSING", "QR_INVALID")


async def test_check_in_with_bogus_qr_fails(worker):
    _, emp = worker
    payload = _evidence()
    payload["qr_token"] = "not-a-real-token"
    resp = await emp.post("/api/v1/attendance/check-in", json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("failure_code") == "QR_INVALID"


async def test_qr_token_is_single_use(worker, admin):
    """A consumed QR token cannot be replayed for a second verification."""
    _, emp = worker
    token = await _qr(admin, "SHOP_CHECKIN")
    payload = _evidence()
    payload["qr_token"] = token
    first = await emp.post("/api/v1/attendance/check-in", json=payload)
    assert first.status_code in (200, 201), first.text
    # same token, second employee -> must be rejected as replayed
    from tests.conftest import create_employee, _new_client, login_ready

    other_body = await create_employee(admin)
    other = _new_client(None)
    await other.__aenter__()
    await login_ready(other, other_body["_username"], other_body["_password"])
    try:
        replay = await other.post("/api/v1/attendance/check-in", json=payload)
        assert replay.status_code == 422, replay.text
        assert replay.json().get("failure_code") == "QR_REPLAYED"
    finally:
        await other.aclose()


async def test_failed_verification_is_persisted(worker, admin):
    """Failed attempts must be recorded for audit (docs/02 DATABASE.md)."""
    from sqlalchemy import func, select
    from app.core.db import get_sessionmaker
    from app.modules.attendance.models import AttendanceVerification

    body, emp = worker
    before = None
    async with get_sessionmaker()() as session:
        before = int(
            (await session.execute(select(func.count()).select_from(AttendanceVerification))).scalar_one()
        )
    resp = await check_in(emp, admin, latitude=FAR_LAT)
    assert resp.status_code == 422
    async with get_sessionmaker()() as session:
        after = int(
            (await session.execute(select(func.count()).select_from(AttendanceVerification))).scalar_one()
        )
    assert after > before


# --------------------------------------------------------------------------- #
# recompute determinism
# --------------------------------------------------------------------------- #
async def test_recompute_is_idempotent(worker, admin):
    body, emp = worker
    r = await check_in(emp, admin)
    record_id = r.json()["id"]
    first = await admin.post(f"/api/v1/attendance/{record_id}/recompute", json={"reason": "test"})
    assert first.status_code == 200, first.text
    second = await admin.post(f"/api/v1/attendance/{record_id}/recompute", json={"reason": "test"})
    assert second.status_code == 200, second.text
    a, b = first.json(), second.json()
    for key in ("worked_seconds", "break_seconds", "overtime_seconds", "day_classification"):
        assert a.get(key) == b.get(key)


# --------------------------------------------------------------------------- #
# corrections
# --------------------------------------------------------------------------- #
async def test_correction_request_and_self_approval_blocked(admin, employee_factory):
    from tests.conftest import create_employee, _new_client, login_ready

    body = await create_employee(admin, roles=["EMPLOYEE", "ADMIN"])
    client = _new_client(None)
    await client.__aenter__()
    await login_ready(client, body["_username"], body["_password"])
    try:
        r = await check_in(client, admin)
        assert r.status_code in (200, 201), r.text
        record_id = r.json()["id"]
        created = await client.post(
            "/api/v1/attendance/corrections",
            json={
                "attendance_record_id": record_id,
                "correction_type": "MISSED_CHECK_OUT",
                "reason": "forgot to check out",
            },
        )
        assert created.status_code in (200, 201), created.text
        correction_id = created.json()["id"]
        resp = await client.post(
            f"/api/v1/attendance/corrections/{correction_id}/approve", json={}
        )
        assert resp.status_code in (403, 422), resp.text
    finally:
        await client.aclose()


# --------------------------------------------------------------------------- #
# break type config is DB-driven
# --------------------------------------------------------------------------- #
async def test_break_types_are_seeded_and_employee_readable(worker):
    _, emp = worker
    resp = await emp.get("/api/v1/break-types")
    assert resp.status_code == 200
    codes = {item["code"] for item in resp.json()["items"]}
    assert {"LUNCH", "TEA"} <= codes


async def test_employee_cannot_create_break_type(worker):
    _, emp = worker
    resp = await emp.post(
        "/api/v1/break-types", json={"code": "X", "name": "X"}
    )
    assert resp.status_code == 403
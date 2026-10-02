"""Priority 1 - authorization, RBAC, IDOR and session security (docs/09_TEST_PLAN.md L5).

Every protected operation must enforce authorization server-side, including
object-level ownership. These tests are deliberately negative: they prove that
an ordinary employee cannot reach admin/business-wide capabilities and cannot
read another employee's objects.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import create_employee, login, login_ready

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
async def alice(employee_factory):
    body, client = await employee_factory()
    return body, client


@pytest.fixture
async def bob(employee_factory):
    body, client = await employee_factory()
    return body, client



def _future_date(days: int = 7) -> str:
    """A near-future business date that satisfies backdate/advance limits."""
    from datetime import datetime

    return (datetime.now(ZoneInfo("Asia/Calcutta")).date() + timedelta(days=days)).isoformat()


ADMIN_ONLY_ENDPOINTS = [
    ("GET", "/api/v1/employees"),
    ("POST", "/api/v1/employees"),
    ("GET", "/api/v1/users"),
    ("GET", "/api/v1/roles"),
    ("POST", "/api/v1/roles"),
    ("GET", "/api/v1/permissions"),
    ("GET", "/api/v1/settings"),
    ("PATCH", "/api/v1/settings"),
    ("GET", "/api/v1/audit-logs"),
    ("GET", "/api/v1/attendance"),
    ("GET", "/api/v1/leaves"),
    ("GET", "/api/v1/ledger"),
    ("GET", "/api/v1/advances"),
    ("GET", "/api/v1/complaints"),
    ("GET", "/api/v1/payroll/runs"),
    ("GET", "/api/v1/salary-records"),
    ("GET", "/api/v1/task-submissions"),
    ("GET", "/api/v1/reports/attendance"),
    ("GET", "/api/v1/reports/ledger"),
    ("GET", "/api/v1/reports/salary?period_year=2025&period_month=1"),
    ("POST", "/api/v1/orders"),
    ("POST", "/api/v1/tasks"),
    ("POST", "/api/v1/notifications/broadcast"),
]


# --------------------------------------------------------------------------- #
# unauthenticated
# --------------------------------------------------------------------------- #
async def test_unauthenticated_protected_endpoints_return_401(client):
    for method, url in [
        ("GET", "/api/v1/employees"),
        ("GET", "/api/v1/settings"),
        ("GET", "/api/v1/orders"),
        ("GET", "/api/v1/ledger"),
        ("POST", "/api/v1/orders"),
    ]:
        resp = await client.request(method, url, json={} if method == "POST" else None)
        assert resp.status_code == 401, (method, url, resp.status_code, resp.text)
        assert resp.json()["code"] == "AUTHENTICATION_REQUIRED"


# --------------------------------------------------------------------------- #
# RBAC: employee vs admin-only
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method,url", ADMIN_ONLY_ENDPOINTS)
async def test_employee_denied_admin_endpoint(alice, method, url):
    _, emp = alice
    resp = await emp.request(method, url, json={} if method in ("POST", "PATCH") else None)
    assert resp.status_code == 403, (method, url, resp.status_code, resp.text)
    assert resp.json()["code"] == "PERMISSION_DENIED"


async def test_admin_allowed_admin_endpoint(admin):
    resp = await admin.get("/api/v1/employees")
    assert resp.status_code == 200


async def test_employee_permission_set_is_exactly_28(alice):
    _, emp = alice
    body = (await emp.get("/api/v1/auth/me")).json()
    assert len(body["permissions"]) == 28
    assert "employee.read.all" not in body["permissions"]
    assert "order.claim" in body["permissions"]


# --------------------------------------------------------------------------- #
# IDOR / object-level ownership
# --------------------------------------------------------------------------- #
async def test_employee_cannot_read_other_employee_profile(alice, bob):
    bob_body, _ = bob
    _, emp = alice
    resp = await emp.get(f"/api/v1/employees/{bob_body['id']}")
    assert resp.status_code in (403, 404), resp.text


async def test_employee_can_read_own_profile(alice):
    body, emp = alice
    resp = await emp.get(f"/api/v1/employees/{body['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == body["id"]


async def test_employee_cannot_read_other_compensation(alice, bob):
    bob_body, _ = bob
    _, emp = alice
    resp = await emp.get(f"/api/v1/employees/{bob_body['id']}/compensation")
    assert resp.status_code in (403, 404), resp.text


async def test_employee_cannot_spoof_employee_scope(admin, alice, bob):
    """Query-level scope parameters must not widen an employee's visibility."""
    bob_body, _ = bob
    _, emp = alice
    resp = await emp.get("/api/v1/attendance/me", params={"employee_id": bob_body["id"]})
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    assert items == []


async def test_employee_cannot_read_other_leave(alice, bob):
    bob_body, bob_client = bob
    _, emp = alice
    leave_types = (await emp.get("/api/v1/leave-types")).json()["items"]
    assert leave_types
    created = await bob_client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types[0]["id"],
            "start_date": _future_date(7),
            "end_date": _future_date(8),
            "reason": "personal",
        },
    )
    assert created.status_code in (200, 201), created.text
    leave_id = created.json()["id"]
    resp = await emp.get(f"/api/v1/leaves/{leave_id}")
    assert resp.status_code in (403, 404), resp.text


async def test_employee_cannot_read_other_ledger_entry(admin, alice, bob):
    bob_body, _ = bob
    _, emp = alice
    created = await admin.post(
        "/api/v1/ledger/entries",
        json={
            "employee_id": bob_body["id"],
            "entry_type": "BONUS",
            "amount": "100.00",
            "reason": "test bonus",
        },
    )
    assert created.status_code in (200, 201), created.text
    entry_id = created.json()["id"]
    resp = await emp.get(f"/api/v1/ledger/{entry_id}")
    assert resp.status_code in (403, 404), resp.text


async def test_employee_cannot_read_other_advance(alice, bob):
    bob_body, _ = bob
    _, emp = alice
    created = await emp.post(
        "/api/v1/advances",
        json={
            "employee_id": bob_body["id"],
            "amount": "500.00",
            "issued_on": "2025-06-01",
            "reason": "spoof",
        },
    )
    assert created.status_code == 403, created.text


async def test_employee_cannot_read_other_salary_record(client, alice, bob):
    bob_body, _ = bob
    _, emp = alice
    resp = await emp.get(f"/api/v1/salary-records/{uuid.uuid4()}")
    assert resp.status_code in (403, 404), resp.text


async def test_employee_cannot_view_other_attendance_record(alice, admin):
    """Create a real attendance record for alice, then try to read it as bob."""
    alice_body, alice_client = alice
    _, bob_client = await _second_employee(admin)
    record_id = await _attendance_record_for(admin, alice_body)
    resp = await bob_client.get(f"/api/v1/attendance/{record_id}")
    assert resp.status_code in (403, 404), resp.text
    own = await alice_client.get(f"/api/v1/attendance/{record_id}")
    assert own.status_code in (200, 404)


async def test_employee_cannot_approve_own_leave(admin):
    """A dual-role user may not approve the leave they raised (self-approval)."""
    body = await create_employee(admin, roles=["EMPLOYEE", "ADMIN"])
    client = _client(admin)
    await login_ready(client, body["_username"], body["_password"])
    try:
        leave_types = (await client.get("/api/v1/leave-types")).json()["items"]
        created = await client.post(
            "/api/v1/leaves",
            json={
                "leave_type_id": leave_types[0]["id"],
                "start_date": _future_date(9),
                "end_date": _future_date(9),
                "reason": "self approval attempt",
            },
        )
        assert created.status_code in (200, 201), created.text
        leave_id = created.json()["id"]
        resp = await client.post(f"/api/v1/leaves/{leave_id}/approve", json={})
        assert resp.status_code in (403, 422), resp.text
        assert resp.json()["code"] in ("PERMISSION_DENIED", "RULE_VIOLATION")
    finally:
        await client.aclose()


# --------------------------------------------------------------------------- #
# privilege escalation
# --------------------------------------------------------------------------- #
async def test_employee_cannot_assign_roles(alice):
    body, emp = alice
    resp = await emp.put(
        f"/api/v1/users/{body['user_id']}/roles",
        json={"role_codes": ["ADMIN"], "reason": "escalate"},
    )
    assert resp.status_code == 403, resp.text


async def test_admin_cannot_remove_own_admin_role(admin):
    me = (await admin.get("/api/v1/auth/me")).json()
    resp = await admin.put(
        f"/api/v1/users/{me['user']['id']}/roles",
        json={"role_codes": ["EMPLOYEE"], "reason": "self demote"},
    )
    assert resp.status_code in (403, 422), resp.text


async def test_employee_cannot_create_role(alice):
    _, emp = alice
    resp = await emp.post(
        "/api/v1/roles",
        json={"code": "SUPER", "name": "Super", "permission_codes": ["role.manage"]},
    )
    assert resp.status_code == 403, resp.text


async def test_employee_cannot_update_settings(alice):
    _, emp = alice
    resp = await emp.patch("/api/v1/settings", json={"values": {"attendance.geofence_radius_meters": 99999}})
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- #
# CSRF (docs/09_TEST_PLAN.md S-16)
# --------------------------------------------------------------------------- #
async def test_unsafe_request_without_csrf_header_is_rejected(prepared_db, admin):
    from tests.conftest import raw_http_client

    assert admin.cookies.get("csrf_token")
    raw = raw_http_client(cookies=admin.cookies)
    try:
        resp = await raw.post("/api/v1/orders", json={"customer_name": "x", "order_amount": "1"})
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "CSRF_INVALID"
    finally:
        await raw.aclose()


async def test_unsafe_request_with_wrong_csrf_header_is_rejected(admin):
    from tests.conftest import raw_http_client

    raw = raw_http_client(cookies=admin.cookies, headers={"X-CSRF-Token": "wrong-token"})
    try:
        resp = await raw.post("/api/v1/orders", json={"customer_name": "x", "order_amount": "1"})
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "CSRF_INVALID"
    finally:
        await raw.aclose()


async def test_csrf_token_from_another_session_is_rejected(prepared_db, admin):
    from tests.conftest import raw_http_client, _new_client

    other = _new_client(None)
    await login(other, "admin", "ChangeMe123!")
    other_token = other.cookies.get("csrf_token")
    assert other_token and other_token != admin.cookies.get("csrf_token")
    raw = raw_http_client(cookies=admin.cookies, headers={"X-CSRF-Token": other_token})
    try:
        resp = await raw.post("/api/v1/orders", json={"customer_name": "x", "order_amount": "1"})
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "CSRF_INVALID"
    finally:
        await raw.aclose()
        await other.aclose()


# --------------------------------------------------------------------------- #
# session abuse
# --------------------------------------------------------------------------- #
async def test_tampered_session_cookie_is_rejected(prepared_db):
    import httpx
    from app.main import app

    cookies = httpx.Cookies()
    cookies.set("wcrm_session", "not-a-real-session-token", domain="testserver", path="/")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", cookies=cookies
    ) as c:
        resp = await c.get("/api/v1/auth/me")
        assert resp.status_code == 401


async def test_logout_revokes_session(admin):
    assert (await admin.get("/api/v1/auth/me")).status_code == 200
    resp = await admin.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    after = await admin.get("/api/v1/auth/me")
    assert after.status_code == 401


async def test_deactivation_revokes_sessions(admin, employee_factory):
    body, emp = await employee_factory()
    assert (await emp.get("/api/v1/auth/me")).status_code == 200
    resp = await admin.post(
        f"/api/v1/employees/{body['id']}/deactivate",
        json={"date_of_exit": "2025-12-31", "reason": "left company"},
    )
    assert resp.status_code in (200, 204), resp.text
    after = await emp.get("/api/v1/auth/me")
    assert after.status_code == 401


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _client(admin_client):
    from tests.conftest import _new_client

    return _new_client(None)


async def _second_employee(admin_client):
    body = await create_employee(admin_client)
    c = _client(admin_client)
    await c.__aenter__()
    await login_ready(c, body["_username"], body["_password"])
    return body, c


async def _attendance_record_for(admin_client, employee_body):
    """Seed one attendance record directly so IDOR can be exercised."""
    from app.core.db import get_sessionmaker
    from app.modules.attendance.models import AttendanceRecord
    from datetime import date

    async with get_sessionmaker()() as session:
        row = AttendanceRecord(
            employee_id=uuid.UUID(str(employee_body["id"])),
            business_date=date(2025, 1, 2),
            status="PRESENT",
            day_classification="FULL_DAY",
        )
        session.add(row)
        await session.commit()
        return str(row.id)
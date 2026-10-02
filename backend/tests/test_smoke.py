"""Harness smoke tests: login, session payload, CSRF, authorization gate."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_login_and_me(admin):
    resp = await admin.get("/api/v1/auth/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["username"] == "admin"
    assert "ADMIN" in body["roles"]
    assert len(body["permissions"]) == 96


async def test_unauthenticated_me_is_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_login_bad_password(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code in (401, 423)


async def test_employee_cannot_read_all_employees(employee_factory):
    body, emp = await employee_factory()
    resp = await emp.get("/api/v1/employees")
    assert resp.status_code == 403
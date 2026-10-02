"""Test fixtures: disposable schema, migrated database, seeded reference data.

The whole suite shares one event loop and one SQLAlchemy engine so that the
async engine's connections stay bound to a single loop (required by psycopg's
async driver).
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import sys
import uuid

if sys.platform == "win32":  # psycopg async cannot run on ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:55432/crm_test"
)
os.environ.setdefault("STORAGE_LOCAL_ROOT", "var/test-storage")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SCHEDULER_ENABLED", "false")

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ChangeMe123!"

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def _reset_schema() -> None:
    from app.core.db import get_engine

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))


@pytest.fixture(scope="session")
async def prepared_db():
    await _reset_schema()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
        )
    from app.core.db import dispose_engine, get_sessionmaker
    from app.seed import ensure_admin, seed_all

    async with get_sessionmaker()() as session:
        await seed_all(session)
        await ensure_admin(session, username=ADMIN_USERNAME, password=ADMIN_PASSWORD)
        # The suite performs many logins/check-ins; raise the per-minute throttles
        # (they are ordinary DB-backed business settings) so only the dedicated
        # rate-limit tests exercise throttling.
        await session.execute(
            text(
                "UPDATE business_settings SET value = '100000'::jsonb "
                "WHERE key LIKE 'security.rate_limit.%'"
            )
        )
        # Shop location is a DB-backed business setting (never hard-coded).
        await session.execute(
            text(
                "UPDATE business_settings SET value = '12.971600'::jsonb "
                "WHERE key = 'attendance.geofence_latitude'"
            )
        )
        await session.execute(
            text(
                "UPDATE business_settings SET value = '77.594600'::jsonb "
                "WHERE key = 'attendance.geofence_longitude'"
            )
        )
        await session.commit()
    yield
    await dispose_engine()


class Api(httpx.AsyncClient):
    """Async client that transparently forwards the CSRF double-submit header."""

    async def request(self, method, url, **kwargs):  # type: ignore[override]
        if method.upper() in UNSAFE_METHODS:
            token = self.cookies.get("csrf_token")
            if token:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", token)
                kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)


def _new_client(prepared_db, cookies: httpx.Cookies | None = None) -> Api:
    from app.main import app

    return Api(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": "http://localhost:3000"},
        cookies=cookies if cookies is not None else httpx.Cookies(),
        timeout=30.0,
    )


@pytest.fixture
async def client(prepared_db):
    """A fresh, unauthenticated API client (own cookie jar)."""
    async with _new_client(prepared_db) as c:
        yield c


@pytest.fixture
def make_client(prepared_db):
    """Factory for additional independent clients (e.g. concurrency tests)."""
    created: list[Api] = []

    def factory() -> Api:
        c = _new_client(prepared_db)
        created.append(c)
        return c

    yield factory


@pytest.fixture
async def db(prepared_db):
    """Direct async DB session for assertions/setup, separate from HTTP clients."""
    from app.core.db import get_sessionmaker

    session = get_sessionmaker()()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


def raw_http_client(cookies=None, headers=None) -> httpx.AsyncClient:
    """A plain httpx client with no CSRF auto-injection (for CSRF tests)."""
    from app.main import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    )


async def login(client: httpx.AsyncClient, username: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, (resp.status_code, resp.text)
    return resp.json()


@pytest.fixture
async def admin(prepared_db):
    """An authenticated administrator client."""
    async with _new_client(prepared_db) as c:
        await login(c, ADMIN_USERNAME, ADMIN_PASSWORD)
        yield c


async def login_ready(
    client: httpx.AsyncClient, username: str, password: str
) -> str:
    """Log in and clear a forced password change.

    Admin-created users start with ``must_change_password = true`` which blocks
    business endpoints (documented behaviour). Returns the effective password.
    """
    payload = await login(client, username, password)
    if payload["user"].get("must_change_password"):
        new_password = password + "A1!"
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": password, "new_password": new_password},
        )
        assert resp.status_code == 204, resp.text
        return new_password
    return password


async def create_employee(
    admin_client: httpx.AsyncClient,
    *,
    code: str | None = None,
    username: str | None = None,
    password: str = "Employee123!",
    roles: list[str] | None = None,
    **extra,
) -> dict:
    """Create an employee (and its user account) through the admin API."""
    suffix = uuid.uuid4().hex[:10]
    code = code or f"EMP{suffix}"
    username = username or f"emp_{suffix}"
    payload = {
        "employee_code": code,
        "full_name": extra.pop("full_name", f"Employee {suffix}"),
        "username": username,
        "email": extra.pop("email", f"{username}@example.com"),
        "date_of_joining": extra.pop("date_of_joining", "2025-01-01"),
        "initial_password": password,
        "roles": roles or ["EMPLOYEE"],
        **extra,
    }
    resp = await admin_client.post("/api/v1/employees", json=payload)
    assert resp.status_code in (200, 201), (resp.status_code, resp.text)
    body = resp.json()
    body["_password"] = password
    body["_username"] = username
    return body


@pytest.fixture
async def employee_factory(admin):
    """Create employee -> login -> return (employee_body, authenticated client)."""
    clients: list[Api] = []

    async def factory(**kwargs):
        body = await create_employee(admin, **kwargs)
        c = _new_client(admin)
        await c.__aenter__()
        clients.append(c)
        body["_password"] = await login_ready(c, body["_username"], body["_password"])
        return body, c

    yield factory

    for c in clients:
        await c.aclose()

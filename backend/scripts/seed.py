"""Idempotent reference-data / permission seeding for the local database.

Usage (from the ``backend/`` directory, with PostgreSQL running):

    python scripts/seed.py

This is safe to run repeatedly and against a populated development database. It
inserts only what is missing (settings, break types, leave types, complaint
categories, the permission catalog and the system roles) and repairs the
ADMIN/EMPLOYEE role -> permission mappings so they match
``app/core/authz.py`` / ``docs/05_PERMISSIONS.md``. It never deletes employees,
attendance, orders or any other business data, so it is the documented way to
repair a database whose role/permission seed has gone stale.

The seed logic itself lives in ``app/seed.py`` (``seed_all`` / ``ensure_admin``);
this module is just the CLI entry point referenced by ``docs/02_DATABASE.md``.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

# Allow ``python scripts/seed.py`` to import the ``app`` package from backend/.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.db import dispose_engine, get_sessionmaker  # noqa: E402
from app.seed import ensure_admin, seed_all  # noqa: E402


async def main() -> int:
    maker = get_sessionmaker()
    async with maker() as session:
        created = await seed_all(session)
        _admin, admin_created = await ensure_admin(session)
        await session.commit()
    await dispose_engine()
    summary = {**created, "admin_created": int(admin_created)}
    print("seed complete:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
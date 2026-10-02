"""Local development server entry point.

On Windows, psycopg's async driver cannot run on the default ProactorEventLoop
(`uvicorn` picks ProactorEventLoop on Windows unless told otherwise). This
runner installs the SelectorEventLoop policy *before* the app (and its async
engine) is created, then serves the FastAPI app.

Usage (from the backend/ directory):
    python run_dev.py
"""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402


def main() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    # Run our own selector loop; do not let uvicorn build a Proactor loop.
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
"""FastAPI application factory (docs/01_ARCHITECTURE.md sections 13-15, 24)."""

from __future__ import annotations

import asyncio
import sys
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import api_router
from app.core.config import get_config
from app.core.db import dispose_engine, get_sessionmaker
from app.core.errors import AppError
from app.core.logging_setup import configure_logging, get_logger
from app.core.timeutil import utcnow

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    config = get_config()
    logger.info("application_startup", extra={"environment": config.environment})
    yield
    await dispose_engine()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    config = get_config()
    app = FastAPI(
        title="Workforce CRM API",
        version="1.0.0",
        docs_url="/api/docs" if not config.is_production else None,
        openapi_url="/api/openapi.json" if not config.is_production else None,
        lifespan=lifespan,
    )

    if config.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key", REQUEST_ID_HEADER],
            expose_headers=[REQUEST_ID_HEADER],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(exc.to_problem(str(request.url.path), request_id)),
            headers={"X-Request-ID": request_id} if request_id else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
                "code": str(error.get("type", "INVALID")),
                "message": str(error.get("msg", "")),
            }
            for error in exc.errors()
        ]
        error = AppError("Request validation failed.")
        error.status_code = 422
        error.code = "VALIDATION_ERROR"
        error.errors = errors
        error.title = "Request validation failed"
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(error.to_problem(str(request.url.path), getattr(request.state, "request_id", None))),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapped = {
            404: "RESOURCE_NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            401: "AUTHENTICATION_REQUIRED",
            403: "PERMISSION_DENIED",
        }.get(exc.status_code, "HTTP_ERROR")
        body = {
            "type": f"https://workforce-crm.local/problems/{mapped.lower().replace('_', '-')}",
            "title": str(exc.detail),
            "status": exc.status_code,
            "code": mapped,
            "detail": str(exc.detail),
            "instance": str(request.url.path),
            "request_id": getattr(request.state, "request_id", None),
        }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": app.version,
            "environment": config.environment,
            "time": utcnow().isoformat(),
        }

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> JSONResponse:
        checks: dict[str, str] = {}
        healthy = True
        try:
            async with get_sessionmaker()() as session:
                await session.execute(text("select 1"))
                migrations = (
                    await session.execute(text("select version_num from alembic_version"))
                ).scalar_one_or_none()
            checks["database"] = "ok"
            checks["migration_head"] = str(migrations)
            expected = config.expected_migration_head
            if expected and migrations and str(migrations) != expected:
                healthy = False
                checks["migration_head"] = f"mismatch (expected {expected})"
        except Exception as exc:  # pragma: no cover - infrastructure failure path
            healthy = False
            checks["database"] = f"error: {exc.__class__.__name__}"
        payload = {"status": "ok" if healthy else "degraded", "checks": checks}
        return JSONResponse(status_code=200 if healthy else 503, content=payload)

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
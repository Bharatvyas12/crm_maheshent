"""Structured JSON logging with secret redaction (section 24)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

REDACT_KEYS = {
    "password",
    "current_password",
    "new_password",
    "password_hash",
    "token",
    "reset_token",
    "qr_token",
    "authorization",
    "cookie",
    "csrf",
    "csrf_token",
    "secret",
    "bank_account_number",
    "p256dh_key",
    "auth_key",
}


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "user_id", "module", "route", "method", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_redact(payload), default=str)


def _redact(value):
    if isinstance(value, dict):
        return {
            key: ("***REDACTED***" if key.lower() in REDACT_KEYS else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

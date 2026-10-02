"""Application error hierarchy and RFC 9457 problem-details handlers."""

from __future__ import annotations

from typing import Any

PROBLEM_BASE = "https://workforce-crm.local/problems"


class AppError(Exception):
    """Base class for every expected application failure."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    title: str = "Internal error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        rule_code: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.rule_code = rule_code
        self.errors = errors
        self.extra = extra or {}

    def to_problem(self, instance: str, request_id: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"{PROBLEM_BASE}/{self.code.lower().replace('_', '-')}",
            "title": self.title,
            "status": self.status_code,
            "code": self.code,
            "detail": self.detail,
            "instance": instance,
        }
        if request_id:
            body["request_id"] = request_id
        if self.errors:
            body["errors"] = self.errors
        if self.rule_code:
            body["rule_code"] = self.rule_code
        body.update(self.extra)
        return body


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    title = "Request validation failed"


class NotFound(AppError):
    status_code = 404
    code = "RESOURCE_NOT_FOUND"
    title = "Resource not found"


class Conflict(AppError):
    status_code = 409
    code = "STATE_CONFLICT"
    title = "State conflict"


class DuplicateConflict(Conflict):
    code = "CONFLICT_DUPLICATE"
    title = "Duplicate resource"


class ClaimAlreadyTaken(Conflict):
    code = "CLAIM_ALREADY_TAKEN"
    title = "Order already claimed"


class IdempotencyConflict(Conflict):
    code = "IDEMPOTENCY_CONFLICT"
    title = "Idempotency key reused with a different payload"


class PermissionDenied(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"
    title = "Permission denied"


class AuthenticationRequired(AppError):
    status_code = 401
    code = "AUTHENTICATION_REQUIRED"
    title = "Authentication required"


class InvalidCredentials(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    title = "Invalid credentials"


class AccountLocked(AppError):
    status_code = 401
    code = "ACCOUNT_LOCKED"
    title = "Account locked"


class AccountDisabled(AppError):
    status_code = 401
    code = "ACCOUNT_DISABLED"
    title = "Account disabled"


class CsrfInvalid(AppError):
    status_code = 403
    code = "CSRF_INVALID"
    title = "CSRF token invalid"


class RuleViolation(AppError):
    status_code = 422
    code = "RULE_VIOLATION"
    title = "Business rule violation"


class PeriodLocked(AppError):
    status_code = 423
    code = "PERIOD_LOCKED"
    title = "Payroll period is locked"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    title = "Too many requests"


class FileTooLarge(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    title = "File too large"


class UnsupportedFileType(AppError):
    status_code = 422
    code = "UNSUPPORTED_FILE_TYPE"
    title = "Unsupported file type"


class StorageUnavailable(AppError):
    status_code = 503
    code = "STORAGE_UNAVAILABLE"
    title = "Storage unavailable"


class DependencyUnavailable(AppError):
    status_code = 503
    code = "DEPENDENCY_UNAVAILABLE"
    title = "Dependency unavailable"
"""Permission catalog, authentication context and server-side authorization.

Mirrors docs/05_PERMISSIONS.md exactly. Deny by default: a route declares a
permission, and the acting user's effective permissions must include it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from fastapi import Request

from app.core.errors import AuthenticationRequired, PermissionDenied

# (code, module, is_sensitive, description)
PERMISSION_CATALOG: list[tuple[str, str, bool, str]] = [
    ("auth.session.read.self", "auth", False, "View own active sessions"),
    ("auth.session.revoke.self", "auth", False, "Revoke own sessions"),
    ("auth.password.change.self", "auth", False, "Change own password"),
    ("employee.manage.credentials", "auth", True, "Trigger a password reset for another user"),
    ("profile.update.self", "directory", False, "Update own permitted profile fields"),
    ("employee.read.self", "directory", False, "Read own employee profile"),
    ("employee.read.all", "directory", False, "Read any employee profile"),
    ("employee.read.sensitive", "directory", True, "Read sensitive employee fields"),
    ("employee.create", "directory", True, "Create employees and their user accounts"),
    ("employee.update", "directory", True, "Update employee profile and employment fields"),
    ("employee.update.sensitive", "directory", True, "Update bank details and sensitive fields"),
    ("employee.deactivate", "directory", True, "Deactivate, reactivate or exit an employee"),
    ("employee.manage.roles", "directory", True, "Assign roles to users"),
    ("role.read", "rbac", False, "Read roles and their permissions"),
    ("role.manage", "rbac", True, "Create, update and delete roles; change permissions"),
    ("permission.read", "rbac", False, "Read the permission catalog"),
    ("settings.read", "settings", False, "Read business settings and the settings schema"),
    ("settings.update", "settings", True, "Change business settings"),
    ("settings.read.history", "settings", True, "Read settings change history"),
    ("attendance.checkin.self", "attendance", False, "Check in"),
    ("attendance.checkout.self", "attendance", False, "Check out"),
    ("attendance.break.self", "attendance", False, "Start/end own breaks"),
    ("attendance.read.self", "attendance", False, "Read own attendance records and events"),
    ("attendance.read.all", "attendance", True, "Read any employee's attendance"),
    ("attendance.manage", "attendance", True, "Record manual attendance events and recompute"),
    ("attendance.config.manage", "attendance", True, "Manage break types and holidays"),
    ("attendance.qr.generate", "attendance", True, "Issue dynamic shop QR tokens"),
    ("attendance.correct.request.self", "attendance", False, "Request a correction to own attendance"),
    ("attendance.correct.approve", "attendance", True, "Approve or reject attendance corrections"),
    ("task.create", "tasks", False, "Create tasks and assign employees"),
    ("task.read.self", "tasks", False, "Read own task assignments and submissions"),
    ("task.read.all", "tasks", False, "Read any task, assignment and submission"),
    ("task.update", "tasks", False, "Update task details and brief attachments"),
    ("task.assign", "tasks", False, "Add or remove assignments"),
    ("task.cancel", "tasks", False, "Cancel a task"),
    ("task.submit.self", "tasks", False, "Start, complete and submit own assignments"),
    ("task.comment", "tasks", False, "Comment on tasks and assignments"),
    ("task.review", "tasks", True, "Approve, reject or request resubmission"),
    ("order.create", "orders", False, "Register orders"),
    ("order.read.available", "orders", False, "See broadcasted orders available to claim"),
    ("order.read.self", "orders", False, "Read orders held by the caller"),
    ("order.read.all", "orders", True, "Read any order, its history and attachments"),
    ("order.update", "orders", False, "Edit order details"),
    ("order.broadcast", "orders", False, "Broadcast or re-broadcast an order"),
    ("order.claim", "orders", False, "Claim and release orders"),
    ("order.update.status.self", "orders", False, "Advance the status of an order the caller holds"),
    ("order.update.status.any", "orders", True, "Advance the status of any order"),
    ("order.proof.upload", "orders", False, "Upload packing/delivery proof"),
    ("order.reassign", "orders", True, "Reassign or force-release an order"),
    ("order.cancel", "orders", True, "Cancel an order"),
    ("leave.apply.self", "leaves", False, "Apply for own leave"),
    ("leave.read.self", "leaves", False, "Read own leave, types and balances"),
    ("leave.read.all", "leaves", True, "Read any employee's leave and balances"),
    ("leave.cancel.self", "leaves", False, "Cancel own leave request"),
    ("leave.cancel.any", "leaves", True, "Cancel any employee's leave"),
    ("leave.approve", "leaves", True, "Approve, reject or request modification"),
    ("leave.type.manage", "leaves", True, "Manage leave types"),
    ("leave.balance.manage", "leaves", True, "Adjust leave balances"),
    ("ledger.read.self", "payroll", True, "Read own ledger entries and balance"),
    ("ledger.read.all", "payroll", True, "Read any employee's ledger"),
    ("ledger.entry.create", "payroll", True, "Post manual ledger entries"),
    ("ledger.entry.adjust", "payroll", True, "Reverse or adjust ledger entries"),
    ("advance.read.self", "payroll", True, "Read own advances"),
    ("advance.read.all", "payroll", True, "Read any employee's advances"),
    ("advance.create", "payroll", True, "Issue an advance"),
    ("advance.approve", "payroll", True, "Approve, reject or write off an advance"),
    ("salary.read.self", "payroll", True, "Read own salary records and payslips"),
    ("salary.read.all", "payroll", True, "Read any employee's salary records"),
    ("salary.compute", "payroll", True, "Create payroll runs and compute salary records"),
    ("salary.finalize", "payroll", True, "Finalize a payroll run and its salary records"),
    ("payroll.lock", "payroll", True, "Lock a payroll period"),
    ("payroll.unlock", "payroll", True, "Unlock a payroll period"),
    ("payroll.pay", "payroll", True, "Mark a payroll run as paid and post payment entries"),
    ("complaint.create.self", "complaints", False, "Submit a complaint"),
    ("complaint.read.self", "complaints", False, "Read own complaints"),
    ("complaint.read.all", "complaints", True, "Read any complaint"),
    ("complaint.read.internal", "complaints", True, "Read internal comments and notes"),
    ("complaint.comment", "complaints", False, "Comment on a complaint"),
    ("complaint.manage", "complaints", True, "Change status, priority, category or assignment"),
    ("complaint.resolve", "complaints", True, "Resolve or reject a complaint"),
    ("complaint.close", "complaints", True, "Close a resolved complaint"),
    ("notification.read.self", "notifications", False, "Read and manage own notifications"),
    ("notification.manage", "notifications", False, "Broadcast notifications and inspect delivery"),
    ("file.upload", "files", False, "Upload files"),
    ("file.read.all", "files", True, "Download any file (subject to entity authorization)"),
    ("file.delete", "files", True, "Delete files not yet referenced"),
    ("report.attendance", "reports", True, "Run attendance, work-hour, break and overtime reports"),
    ("report.tasks", "reports", False, "Run task reports"),
    ("report.orders", "reports", False, "Run order reports"),
    ("report.leaves", "reports", True, "Run leave reports"),
    ("report.ledger", "reports", True, "Run ledger and advance reports"),
    ("report.salary", "reports", True, "Run salary reports"),
    ("report.complaints", "reports", True, "Run complaint reports"),
    ("report.export", "reports", True, "Generate and download report exports"),
    ("audit.read", "audit", True, "Read the audit log"),
    ("audit.export", "audit", True, "Export the audit log"),
]

Permission = Enum(
    "Permission",
    {code.upper().replace(".", "_"): code for code, _m, _s, _d in PERMISSION_CATALOG},
    type=str,
)

ALL_PERMISSION_CODES: frozenset[str] = frozenset(code for code, _m, _s, _d in PERMISSION_CATALOG)

SENSITIVE_PERMISSION_CODES: frozenset[str] = frozenset(
    code for code, _m, _s, _d in PERMISSION_CATALOG if _s
)

# docs/05_PERMISSIONS.md section 4.2 - exactly 28 permissions.
EMPLOYEE_PERMISSION_CODES: frozenset[str] = frozenset(
    {
        "auth.session.read.self",
        "auth.session.revoke.self",
        "auth.password.change.self",
        "profile.update.self",
        "employee.read.self",
        "attendance.checkin.self",
        "attendance.checkout.self",
        "attendance.break.self",
        "attendance.read.self",
        "attendance.correct.request.self",
        "task.read.self",
        "task.submit.self",
        "task.comment",
        "order.read.available",
        "order.read.self",
        "order.claim",
        "order.update.status.self",
        "order.proof.upload",
        "leave.apply.self",
        "leave.read.self",
        "leave.cancel.self",
        "ledger.read.self",
        "advance.read.self",
        "complaint.create.self",
        "complaint.read.self",
        "complaint.comment",
        "notification.read.self",
        "file.upload",
    }
)


@dataclass(slots=True)
class AuthContext:
    """The authenticated actor for the current request."""

    user_id: uuid.UUID
    username: str
    session_id: uuid.UUID
    permissions: frozenset[str] = field(default_factory=frozenset)
    roles: tuple[str, ...] = ()
    employee_id: uuid.UUID | None = None
    must_change_password: bool = False

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any(self, *permissions: str) -> bool:
        return any(p in self.permissions for p in permissions)


def get_auth(request: Request) -> AuthContext | None:
    return getattr(request.state, "auth", None)


def current_auth(request: Request) -> AuthContext:
    auth = get_auth(request)
    if auth is None:
        raise AuthenticationRequired("A valid session is required.")
    return auth


# Endpoints that remain usable while `must_change_password` is set.
PASSWORD_CHANGE_ALLOWED_PATHS = frozenset(
    {
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/auth/logout",
        "/api/v1/auth/sessions",
    }
)


def require_permission(permission: str) -> Callable[[Request], AuthContext]:
    """Dependency factory enforcing a route permission from the catalog."""

    def dependency(request: Request) -> AuthContext:
        auth = current_auth(request)
        if not auth.has(permission):
            raise PermissionDenied(f"Missing permission: {permission}")
        if auth.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
            raise PermissionDenied(
                "A password change is required before using the application.",
                rule_code="PASSWORD_CHANGE_REQUIRED",
            )
        return auth

    return dependency


def require_any_permission(*permissions: str) -> Callable[[Request], AuthContext]:
    def dependency(request: Request) -> AuthContext:
        auth = current_auth(request)
        if not auth.has_any(*permissions):
            raise PermissionDenied("Missing required permission: " + " or ".join(permissions))
        return auth

    return dependency


def assert_self_or_permission(auth: AuthContext, owner_employee_id: Any, permission: str) -> None:
    """Object-level authorization helper: employee may touch own records only."""
    if auth.has(permission):
        return
    if owner_employee_id is not None and str(owner_employee_id) == str(auth.employee_id):
        return
    raise PermissionDenied("You may only access your own records.")
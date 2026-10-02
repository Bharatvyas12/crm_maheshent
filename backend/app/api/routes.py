"""Aggregated API router: the composition root registers every module's router."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.attendance.router import router as attendance_router
from app.modules.audit.router import router as audit_router
from app.modules.complaints.router import router as complaints_router
from app.modules.directory.router import router as directory_router
from app.modules.files.router import router as files_router
from app.modules.identity.router import router as identity_router
from app.modules.leaves.router import router as leaves_router
from app.modules.notifications.router import router as notifications_router
from app.modules.orders.router import router as orders_router
from app.modules.payroll.router import router as payroll_router
from app.modules.rbac.router import router as rbac_router
from app.modules.reports.router import router as reports_router
from app.modules.settings.router import router as settings_router
from app.modules.tasks.router import router as tasks_router

api_router = APIRouter()

api_router.include_router(identity_router)
api_router.include_router(directory_router)
api_router.include_router(rbac_router)
api_router.include_router(settings_router)
api_router.include_router(attendance_router)
api_router.include_router(tasks_router)
api_router.include_router(orders_router)
api_router.include_router(leaves_router)
api_router.include_router(payroll_router)
api_router.include_router(complaints_router)
api_router.include_router(notifications_router)
api_router.include_router(files_router)
api_router.include_router(reports_router)
api_router.include_router(audit_router)
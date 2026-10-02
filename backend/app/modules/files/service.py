"""Files service: upload, private storage, signed downloads, reference checks."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, PermissionDenied, RuleViolation, UnsupportedFileType, ValidationError
from app.core.storage import (
    build_storage_key,
    delete_object,
    read_object,
    sniff_matches,
    put_object,
)
from app.core.timeutil import utcnow
from app.modules.files.models import File
from app.modules.settings.service import SettingsView

EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/csv": "csv",
    "text/plain": "txt",
}


def serialize_file(row: File) -> dict[str, Any]:
    return {
        "id": row.id,
        "original_name": row.original_name,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "checksum_sha256": row.checksum_sha256,
        "purpose": row.purpose,
        "scan_status": row.scan_status,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "uploaded_by": row.uploaded_by,
        "created_at": row.created_at,
    }


async def get_file(session: AsyncSession, file_id: uuid.UUID) -> File:
    row = await session.get(File, file_id)
    if row is None or row.deleted_at is not None:
        raise NotFound("File not found.")
    return row


async def assert_exists(session: AsyncSession, file_id: uuid.UUID) -> File:
    return await get_file(session, file_id)


async def create_file(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    purpose: str,
    original_name: str,
    content_type: str,
    data: bytes,
    settings: SettingsView,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> File:
    max_bytes = settings.int_("files.max_upload_mb") * 1024 * 1024
    if len(data) > max_bytes:
        from app.core.errors import FileTooLarge

        raise FileTooLarge(f"Files must be at most {settings.int_('files.max_upload_mb')} MB.")
    allowed = settings.json_("files.allowed_mime_types") or []
    if allowed and content_type not in allowed:
        raise UnsupportedFileType(f"Content type {content_type} is not allowed.")
    extension = EXTENSION_BY_MIME.get(content_type, "bin")
    if not sniff_matches(content_type, data[:32]):
        raise UnsupportedFileType("The file content does not match its declared type.")
    key = build_storage_key(purpose.lower(), extension)
    stored = put_object(key, data)
    row = File(
        storage_key=stored.storage_key,
        original_name=original_name[:255],
        content_type=content_type,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,
        purpose=purpose,
        scan_status="NOT_SCANNED",
        uploaded_by=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(row)
    await session.flush()
    return row


async def count_for_entity(
    session: AsyncSession, *, entity_type: str, entity_id: uuid.UUID
) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(File)
                .where(
                    File.entity_type == entity_type,
                    File.entity_id == entity_id,
                    File.deleted_at.is_(None),
                )
            )
        ).scalar_one()
    )


async def read_file(row: File) -> bytes:
    return read_object(row.storage_key)


async def delete_file(session: AsyncSession, row: File) -> None:
    if row.entity_type is not None and row.entity_id is not None:
        raise RuleViolation(
            "A referenced file cannot be deleted.", rule_code="FILE_REFERENCED"
        )
    row.deleted_at = utcnow()
    delete_object(row.storage_key)
    await session.flush()


async def authorize_file_access(session: AsyncSession, *, file_id: uuid.UUID, auth) -> File:
    """Object-level authorization for file download (no IDOR)."""
    row = await get_file(session, file_id)
    if auth.has("file.read.all"):
        return row
    if auth.user_id == row.uploaded_by:
        return row
    if row.entity_type == "employee" and str(row.entity_id) == str(auth.employee_id):
        return row
    raise PermissionDenied("You are not allowed to access this file.")
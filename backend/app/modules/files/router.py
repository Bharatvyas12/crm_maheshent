"""Files endpoints (docs/03_API_CONTRACT.md section 14)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel

from app.api.context import Ctx, require, require_authenticated
from app.core.config import get_config
from app.core.errors import PermissionDenied, ValidationError
from app.core.storage import issue_download_token, verify_download_token
from app.modules.files import service
from app.modules.files.models import FILE_PURPOSES

router = APIRouter(tags=["files"])


class DeleteRequest(BaseModel):
    reason: str | None = None


@router.post("/files", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    purpose: str = Form(...),
    entity_type: str | None = Form(None),
    entity_id: uuid.UUID | None = Form(None),
    ctx: Ctx = Depends(require("file.upload")),
) -> dict:
    if purpose not in FILE_PURPOSES:
        raise ValidationError(f"Unsupported purpose: {purpose}")
    data = await file.read()
    row = await service.create_file(
        ctx.session,
        actor_user_id=ctx.actor_user_id,
        purpose=purpose,
        original_name=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        settings=ctx.settings,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    await ctx.audit(
        category="FILE",
        action="file.uploaded",
        entity_type="file",
        entity_id=row.id,
        after={"purpose": row.purpose, "size_bytes": row.size_bytes},
    )
    return service.serialize_file(row)


@router.get("/files/{file_id}")
async def download_file(file_id: uuid.UUID, ctx: Ctx = Depends(require_authenticated)) -> Response:
    row = await service.authorize_file_access(ctx.session, file_id=file_id, auth=ctx.actor)
    data = await service.read_file(row)
    return Response(
        content=data,
        media_type=row.content_type,
        headers={"Content-Disposition": f'inline; filename="{row.original_name}"'},
    )


@router.get("/files/{file_id}/url")
async def file_url(file_id: uuid.UUID, ctx: Ctx = Depends(require_authenticated)) -> dict:
    await service.authorize_file_access(ctx.session, file_id=file_id, auth=ctx.actor)
    ttl = ctx.settings.int_("files.presigned_url_ttl_seconds")
    token, expires_at = issue_download_token(str(file_id), ttl)
    return {
        "file_id": file_id,
        "url": f"/api/v1/files/{file_id}/download?token={token}",
        "expires_at": expires_at,
    }


@router.get("/files/{file_id}/download")
async def download_with_token(
    file_id: uuid.UUID, token: str = Query(...), ctx: Ctx = Depends(require_authenticated)
) -> Response:
    if not verify_download_token(str(file_id), token):
        raise PermissionDenied("This download link is invalid or has expired.")
    row = await service.get_file(ctx.session, file_id)
    data = await service.read_file(row)
    return Response(content=data, media_type=row.content_type)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID, reason: str | None = Query(None), ctx: Ctx = Depends(require("file.upload"))
) -> Response:
    row = await service.get_file(ctx.session, file_id)
    if row.uploaded_by != ctx.actor_user_id and not ctx.actor.has("file.delete"):
        raise PermissionDenied("You may only delete files you uploaded.")
    await service.delete_file(ctx.session, row)
    await ctx.audit(
        category="FILE",
        action="file.deleted",
        entity_type="file",
        entity_id=row.id,
        reason=reason,
    )
    return Response(status_code=204)
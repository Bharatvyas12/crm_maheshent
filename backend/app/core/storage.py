"""Object storage abstraction with short-lived signed download URLs.

The MVP uses a private local filesystem root; the interface matches the S3-style
contract in docs/01_ARCHITECTURE.md section 14 so a bucket can be swapped in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_config
from app.core.errors import StorageUnavailable

MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
    "application/pdf": (b"%PDF",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (b"PK\x03\x04",),
    "text/csv": (b"",),
    "text/plain": (b"",),
}


@dataclass(slots=True)
class StoredObject:
    storage_key: str
    size_bytes: int
    checksum_sha256: str


def _root() -> Path:
    root = Path(get_config().storage_local_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[3] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_storage_key(module: str, extension: str) -> str:
    now = time.gmtime()
    return f"{module}/{now.tm_year:04d}/{now.tm_mon:02d}/{uuid.uuid4().hex}.{extension.lstrip('.')}"


def sniff_matches(content_type: str, head: bytes) -> bool:
    signatures = MAGIC_SIGNATURES.get(content_type)
    if signatures is None:
        return False
    if signatures == (b"",):
        return True
    return any(head.startswith(sig) for sig in signatures)


def put_object(storage_key: str, data: bytes) -> StoredObject:
    try:
        path = _root() / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:  # pragma: no cover - filesystem failure path
        raise StorageUnavailable("Unable to persist the uploaded object.") from exc
    return StoredObject(
        storage_key=storage_key,
        size_bytes=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )


def read_object(storage_key: str) -> bytes:
    path = _root() / storage_key
    if not path.is_file():
        raise StorageUnavailable("Object is no longer available.")
    return path.read_bytes()


def delete_object(storage_key: str) -> None:
    path = _root() / storage_key
    if path.is_file():
        os.remove(path)


def _sign(payload: str) -> str:
    key = get_config().signing_key.encode("utf-8")
    digest = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_download_token(file_id: str, ttl_seconds: int) -> tuple[str, int]:
    expires_at = int(time.time()) + int(ttl_seconds)
    payload = f"{file_id}:{expires_at}"
    return f"{payload}:{_sign(payload)}", expires_at


def verify_download_token(file_id: str, token: str) -> bool:
    try:
        token_file, expires_raw, signature = token.rsplit(":", 2)
    except ValueError:
        return False
    if token_file != str(file_id):
        return False
    if int(expires_raw) < int(time.time()):
        return False
    return hmac.compare_digest(signature, _sign(f"{token_file}:{expires_raw}"))
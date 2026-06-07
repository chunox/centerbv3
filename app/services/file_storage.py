"""Almacenamiento local de adjuntos binarios (§4.11)."""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def attachment_download_path(attachment_id: uuid.UUID) -> str:
    return f"/api/v1/attachments/{attachment_id}/file"


def is_stored_attachment(url: str) -> bool:
    return url.startswith("/api/v1/attachments/") and url.endswith("/file")


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    cleaned = _UNSAFE_NAME.sub("_", base).strip("._")
    return cleaned or "archivo"


def attachment_storage_dir(attachment_id: uuid.UUID) -> Path:
    return settings.uploads_path / str(attachment_id)


def stored_file_path(attachment_id: uuid.UUID, nombre_original: str) -> Path:
    return attachment_storage_dir(attachment_id) / _sanitize_filename(nombre_original)


async def read_upload_limited(file: UploadFile, *, max_bytes: int) -> tuple[bytes, str]:
    if not file.filename:
        raise HTTPException(status_code=422, detail="El archivo debe tener nombre")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 64)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo supera el máximo de {max_bytes} bytes",
            )
        chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise HTTPException(status_code=422, detail="El archivo está vacío")

    mime_type = file.content_type or "application/octet-stream"
    return content, mime_type


def save_attachment_file(
    attachment_id: uuid.UUID,
    nombre_original: str,
    content: bytes,
) -> Path:
    dest_dir = attachment_storage_dir(attachment_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = stored_file_path(attachment_id, nombre_original)
    dest.write_bytes(content)
    return dest


def resolve_stored_file(attachment_id: uuid.UUID, nombre_original: str) -> Path | None:
    path = stored_file_path(attachment_id, nombre_original)
    return path if path.is_file() else None


def rename_stored_file(
    attachment_id: uuid.UUID,
    nombre_anterior: str,
    nombre_nuevo: str,
) -> None:
    old_path = stored_file_path(attachment_id, nombre_anterior)
    if not old_path.is_file():
        return
    new_path = stored_file_path(attachment_id, nombre_nuevo)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)


def delete_attachment_storage(attachment_id: uuid.UUID) -> None:
    dest_dir = attachment_storage_dir(attachment_id)
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir, ignore_errors=True)

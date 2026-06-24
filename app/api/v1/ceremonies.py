"""
Ceremonias Scrum — CRUD + SSE real-time.

Modelo:
  ScrumCeremonySession: session_type (planning|daily|retro|review), status, sprint_id
  ScrumCeremonyEntry:   author_id, entry_type, payload (JSON)

SSE: cada cliente conectado a /stream recibe los nuevos entries en tiempo real.
     El broker es in-memory (asyncio.Queue) — suficiente para dev, un solo proceso.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import ScrumCeremonyEntry, ScrumCeremonySession, User
from app.services.access import require_capability, require_project_member

router = APIRouter()

# ─── In-memory SSE broker ─────────────────────────────────────────────────────
# session_id → list[asyncio.Queue]
_SUBSCRIBERS: dict[str, list[asyncio.Queue]] = {}


def _publish(session_id: str, event: dict) -> None:
    for q in _SUBSCRIBERS.get(session_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def _subscribe(session_id: str) -> AsyncGenerator[dict, None]:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _SUBSCRIBERS.setdefault(session_id, []).append(q)
    try:
        while True:
            event = await q.get()
            yield event
    finally:
        _SUBSCRIBERS.get(session_id, []).remove(q)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CeremonySessionResponse(BaseModel):
    id: str
    project_id: str
    sprint_id: str | None
    session_type: str
    status: str
    started_at: str | None
    closed_at: str | None
    created_by: str
    created_at: str
    entry_count: int


class CeremonyEntryResponse(BaseModel):
    id: str
    session_id: str
    author_id: str
    author_name: str
    entry_type: str
    payload: dict
    created_at: str
    updated_at: str


class CreateSessionBody(BaseModel):
    session_type: str        # planning | daily | retro | review
    sprint_id: str | None = None


class CreateEntryBody(BaseModel):
    entry_type: str          # vote | standup | retro_item | note
    payload: dict


class UpdateEntryBody(BaseModel):
    payload: dict


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _session_to_resp(s: ScrumCeremonySession, entry_count: int) -> CeremonySessionResponse:
    return CeremonySessionResponse(
        id=s.id,
        project_id=s.project_id,
        sprint_id=s.sprint_id,
        session_type=s.session_type,
        status=s.status,
        started_at=s.started_at.isoformat() if s.started_at else None,
        closed_at=s.closed_at.isoformat() if s.closed_at else None,
        created_by=s.created_by,
        created_at=s.created_at.isoformat(),
        entry_count=entry_count,
    )


def _entry_to_resp(e: ScrumCeremonyEntry, db: Session) -> CeremonyEntryResponse:
    author = db.query(User).filter(User.id == e.author_id).first()
    return CeremonyEntryResponse(
        id=e.id,
        session_id=e.session_id,
        author_id=e.author_id,
        author_name=author.nombre if author else "?",
        entry_type=e.entry_type,
        payload=e.payload or {},
        created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat(),
    )


def _get_session_or_404(db: Session, project_id: str, session_id: str) -> ScrumCeremonySession:
    s = db.query(ScrumCeremonySession).filter(
        ScrumCeremonySession.id == session_id,
        ScrumCeremonySession.project_id == project_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return s


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/ceremonies", response_model=list[CeremonySessionResponse])
def list_ceremonies(
    project_id: str,
    session_type: str | None = None,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    q = db.query(ScrumCeremonySession).filter(ScrumCeremonySession.project_id == project_id)
    if session_type:
        q = q.filter(ScrumCeremonySession.session_type == session_type)
    sessions = q.order_by(ScrumCeremonySession.created_at.desc()).all()
    return [
        _session_to_resp(s, db.query(ScrumCeremonyEntry).filter(ScrumCeremonyEntry.session_id == s.id).count())
        for s in sessions
    ]


@router.post("/{project_id}/ceremonies", response_model=CeremonySessionResponse, status_code=201)
def create_ceremony(
    project_id: str,
    body: CreateSessionBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "ceremony.create")
    session = ScrumCeremonySession(
        project_id=project_id,
        sprint_id=body.sprint_id,
        session_type=body.session_type,
        status="pendiente",
        created_by=actor_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_resp(session, 0)


@router.get("/{project_id}/ceremonies/{session_id}", response_model=CeremonySessionResponse)
def get_ceremony(
    project_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    s = _get_session_or_404(db, project_id, session_id)
    count = db.query(ScrumCeremonyEntry).filter(ScrumCeremonyEntry.session_id == session_id).count()
    return _session_to_resp(s, count)


@router.post("/{project_id}/ceremonies/{session_id}/start", response_model=CeremonySessionResponse)
def start_ceremony(
    project_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "ceremony.start")
    s = _get_session_or_404(db, project_id, session_id)
    if s.status != "pendiente":
        raise HTTPException(409, "La sesión ya fue iniciada")
    s.status = "activa"
    s.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    _publish(session_id, {"type": "session_started", "session_id": session_id})
    count = db.query(ScrumCeremonyEntry).filter(ScrumCeremonyEntry.session_id == session_id).count()
    return _session_to_resp(s, count)


@router.post("/{project_id}/ceremonies/{session_id}/close", response_model=CeremonySessionResponse)
def close_ceremony(
    project_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "ceremony.close")
    s = _get_session_or_404(db, project_id, session_id)
    if s.status == "cerrada":
        raise HTTPException(409, "La sesión ya está cerrada")
    s.status = "cerrada"
    s.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    _publish(session_id, {"type": "session_closed", "session_id": session_id})
    count = db.query(ScrumCeremonyEntry).filter(ScrumCeremonyEntry.session_id == session_id).count()
    return _session_to_resp(s, count)


# ─── Entries ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/ceremonies/{session_id}/entries", response_model=list[CeremonyEntryResponse])
def list_entries(
    project_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    _get_session_or_404(db, project_id, session_id)
    entries = (
        db.query(ScrumCeremonyEntry)
        .filter(ScrumCeremonyEntry.session_id == session_id)
        .order_by(ScrumCeremonyEntry.created_at)
        .all()
    )
    return [_entry_to_resp(e, db) for e in entries]


@router.post("/{project_id}/ceremonies/{session_id}/entries",
             response_model=CeremonyEntryResponse, status_code=201)
def add_entry(
    project_id: str,
    session_id: str,
    body: CreateEntryBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    _get_session_or_404(db, project_id, session_id)
    entry = ScrumCeremonyEntry(
        session_id=session_id,
        author_id=actor_id,
        entry_type=body.entry_type,
        payload=body.payload,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    resp = _entry_to_resp(entry, db)
    _publish(session_id, {"type": "entry_added", "entry": resp.model_dump()})
    return resp


@router.put("/{project_id}/ceremonies/{session_id}/entries/{entry_id}",
            response_model=CeremonyEntryResponse)
def update_entry(
    project_id: str,
    session_id: str,
    entry_id: str,
    body: UpdateEntryBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    _get_session_or_404(db, project_id, session_id)
    entry = db.query(ScrumCeremonyEntry).filter(
        ScrumCeremonyEntry.id == entry_id,
        ScrumCeremonyEntry.session_id == session_id,
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    entry.payload = {**(entry.payload or {}), **body.payload}
    db.commit()
    db.refresh(entry)
    resp = _entry_to_resp(entry, db)
    _publish(session_id, {"type": "entry_updated", "entry": resp.model_dump()})
    return resp


@router.delete("/{project_id}/ceremonies/{session_id}/entries/{entry_id}", status_code=204)
def delete_entry(
    project_id: str,
    session_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    _get_session_or_404(db, project_id, session_id)
    entry = db.query(ScrumCeremonyEntry).filter(
        ScrumCeremonyEntry.id == entry_id,
        ScrumCeremonyEntry.session_id == session_id,
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    db.delete(entry)
    db.commit()
    _publish(session_id, {"type": "entry_deleted", "entry_id": entry_id})


# ─── SSE Stream ───────────────────────────────────────────────────────────────

@router.get("/{project_id}/ceremonies/{session_id}/stream")
async def ceremony_stream(
    request: Request,
    project_id: str,
    session_id: str,
    token: str | None = Query(None, description="JWT access token (para EventSource que no puede enviar headers)"),
    db: Session = Depends(get_db),
):
    """
    Server-Sent Events stream para la sesión.
    Emite: entry_added, entry_updated, entry_deleted, session_started, session_closed.
    Acepta token vía query param ?token=... (EventSource no soporta Authorization header).
    """
    from app.services.auth_service import decode_token
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")
    try:
        actor_id = decode_token(token, expected_type="access")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    require_project_member(db, actor_id, project_id)
    _get_session_or_404(db, project_id, session_id)

    async def generator():
        # Evento inicial — confirma conexión
        yield {"event": "connected", "data": json.dumps({"session_id": session_id})}
        async for event in _subscribe(session_id):
            if await request.is_disconnected():
                break
            yield {"event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(generator())

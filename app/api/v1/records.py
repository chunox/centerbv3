from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import ProjectRecord, ProjectRecordBlocker, ProjectRecordDependency
from app.services.access import get_member_context, require_capability, require_project_member
from app.services.capability_map import (
    capability_for_record_create,
    capability_for_record_delete,
    capability_for_record_edit,
    capability_for_transition,
)
from app.services.blockers import sync_block_on_create, sync_unblock_on_resolve
from app.schemas.blockers import BlockerResponse, CreateBlockerRequest, ResolveBlockerRequest
from app.schemas.records import (
    CascadePreviewResponse,
    CascadeChildPreview,
    CreateRecordRequest,
    MisalignedStoryPreview,
    RecordListResponse,
    RecordResponse,
    ReorderRequest,
    TransitionPreviewRequest,
    TransitionRequest,
    UpdateRecordRequest,
)
from app.services.records.store import (
    create_record,
    delete_record,
    get_record,
    list_records,
    reorder_records,
    update_record,
)
from app.services.workflow.engine import apply_transition
from app.services.workflow.side_effects import cancel_all_descendants, reopen_direct_done_children
from app.services.workflow.cascade import (
    apply_cascade_transition,
    preview_cascade_transition,
    resolve_cascade_mode,
)
from app.services.audit import write_audit

router = APIRouter()


# ─── Dependency schemas (defined here to avoid extra files) ───────────────────

class DependencyResponse(BaseModel):
    id: str
    predecessor_id: str
    successor_id: str
    created_by: str
    created_at: str


class CreateDependencyRequest(BaseModel):
    predecessor_id: str
    successor_id: str


class DependenciesPayload(BaseModel):
    predecessors: list[DependencyResponse]
    successors: list[DependencyResponse]


def _dep_to_response(d: ProjectRecordDependency) -> DependencyResponse:
    return DependencyResponse(
        id=d.id,
        predecessor_id=d.predecessor_id,
        successor_id=d.successor_id,
        created_by=d.created_by,
        created_at=d.created_at.isoformat(),
    )


def _blocker_to_response(b: ProjectRecordBlocker) -> BlockerResponse:
    return BlockerResponse(
        id=b.id,
        record_id=b.record_id,
        project_id=b.project_id,
        description=b.description,
        created_by=b.created_by,
        created_at=b.created_at,
        resolved_at=b.resolved_at,
        resolved_by=b.resolved_by,
        resolution_note=b.resolution_note,
        is_resolved=b.resolved_at is not None,
    )


# ─── Records CRUD ─────────────────────────────────────────────────────────────

@router.get("/{project_id}/records", response_model=RecordListResponse)
def list_project_records(
    project_id: str,
    record_type: str | None = Query(None),
    parent_id: str | None = Query(None),
    status: str | None = Query(None),
    sprint_id: str | None = Query(None),
    q: str | None = Query(None, description="Búsqueda por título (substring)"),
    limit: int = Query(1000, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    return list_records(
        db,
        project_id=str(project_id),
        record_type=record_type,
        parent_id=parent_id,
        status=status,
        sprint_id=sprint_id,
        search=q,
        limit=limit,
        offset=offset,
    )


@router.post("/{project_id}/records", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
def create_project_record(
    project_id: str,
    body: CreateRecordRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, capability_for_record_create(body.record_type, body.extra))
    record = create_record(db, project, body, actor_id)
    write_audit(db, project=project, actor_id=actor_id, entity_type=body.record_type,
                entity_id=record.id, action="created", changes={"title": record.title})
    db.commit()
    return record


@router.get("/{project_id}/records/{record_id}", response_model=RecordResponse)
def get_project_record(
    project_id: str,
    record_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    return get_record(db, str(project_id), str(record_id))


@router.patch("/{project_id}/records/{record_id}", response_model=RecordResponse)
def update_project_record(
    project_id: str,
    record_id: str,
    body: UpdateRecordRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    record_orm = db.query(ProjectRecord).filter(
        ProjectRecord.id == str(record_id),
        ProjectRecord.project_id == str(project_id),
    ).first()
    if not record_orm:
        raise HTTPException(status_code=404, detail="Record no encontrado")
    require_capability(ctx, capability_for_record_edit(record_orm))
    project = get_project_or_404(db, project_id)
    prev_title = record_orm.title
    result = update_record(db, str(project_id), str(record_id), body)
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type=record_orm.record_type, entity_id=str(record_id), action="updated",
        changes={"title": [prev_title, result.title] if body.title is not None else {}},
    )
    db.commit()
    return result


@router.delete("/{project_id}/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_record(
    project_id: str,
    record_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    record_orm = db.query(ProjectRecord).filter(
        ProjectRecord.id == str(record_id),
        ProjectRecord.project_id == str(project_id),
    ).first()
    if record_orm:
        delete_cap = capability_for_record_delete(record_orm)
        if delete_cap:
            require_capability(ctx, delete_cap)
        else:
            raise HTTPException(status_code=403, detail="Sin permiso para eliminar este tipo de record")
        write_audit(db, project=project, actor_id=actor_id,
                    entity_type=record_orm.record_type, entity_id=str(record_id),
                    action="deleted", changes={"title": record_orm.title})
        db.commit()
    delete_record(db, str(project_id), str(record_id))


def _child_preview(c) -> CascadeChildPreview:
    return CascadeChildPreview(
        id=c.id,
        title=c.title,
        entity_type=c.entity_type,
        scrum_role=c.scrum_role,
        from_status=c.from_status,
        to_status=c.to_status,
        action_id=c.action_id,
        can_transition=c.can_transition,
        is_blocked=c.is_blocked,
        reason=c.reason,
    )


def _cascade_preview_response(preview, *, requires_sprint_assignment=False, active_sprint_id=None):
    return CascadePreviewResponse(
        record_id=preview.record_id,
        title=preview.title,
        entity_type=preview.entity_type,
        scrum_role=preview.scrum_role,
        from_status=preview.from_status,
        to_status=preview.to_status,
        action_id=preview.action_id,
        children=[_child_preview(c) for c in preview.children],
        requires_confirmation=preview.requires_confirmation,
        requires_sprint_assignment=requires_sprint_assignment,
        active_sprint_id=active_sprint_id,
        epic_done_blocked=preview.epic_done_blocked,
        stories_misaligned=[
            MisalignedStoryPreview(id=s["id"], title=s["title"], status=s["status"])
            for s in preview.stories_misaligned
        ],
        blocked_in_chain=preview.blocked_in_chain,
        children_ahead=[_child_preview(c) for c in preview.children_ahead],
        epic_done_misaligned=preview.epic_done_misaligned,
        cascade_modes_available=preview.cascade_modes_available,
    )


@router.post(
    "/{project_id}/records/{record_id}/transition/preview",
    response_model=CascadePreviewResponse,
)
def preview_transition(
    project_id: str,
    record_id: str,
    body: TransitionPreviewRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    from app.services.records.store import _load_query
    from app.services.scrum.transition_helpers import (
        ensure_sprint_for_transition,
        get_transition_for_record,
    )
    from app.services.workflow.engine import _resolve_entity_type
    from app.domain.packs.definitions import TEMPLATE_TO_PACK

    record_orm = (
        _load_query(db, str(project_id))
        .filter(ProjectRecord.id == str(record_id))
        .first()
    )
    if not record_orm:
        raise HTTPException(status_code=404, detail="Record no encontrado")
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    entity_type = _resolve_entity_type(record_orm, pack_key)
    trans_cap = capability_for_transition(entity_type, body.action_id)
    if trans_cap:
        require_capability(ctx, trans_cap)

    needs_sprint, active_id = ensure_sprint_for_transition(
        db, project, record_orm, body.action_id, body.sprint_id,
    )
    if needs_sprint:
        _, _, transition = get_transition_for_record(project, record_orm, body.action_id)
        return CascadePreviewResponse(
            record_id=str(record_orm.id),
            title=record_orm.title,
            entity_type=entity_type,
            scrum_role=(record_orm.extra or {}).get("scrum_role") or entity_type,
            from_status=record_orm.status,
            to_status=transition.to_state,
            action_id=body.action_id,
            children=[],
            requires_confirmation=False,
            requires_sprint_assignment=True,
            active_sprint_id=active_id,
        )

    preview = preview_cascade_transition(db, project, record_orm, body.action_id)
    return _cascade_preview_response(preview, active_sprint_id=active_id)


@router.post("/{project_id}/records/{record_id}/transition", response_model=RecordResponse)
def transition_record(
    project_id: str,
    record_id: str,
    body: TransitionRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    from app.services.records.store import _load_query, _to_response
    from app.services.scrum.epic_invariants import assert_epic_done_allowed
    from app.services.scrum.transition_helpers import (
        ensure_sprint_for_transition,
        raise_requires_sprint_assignment,
    )
    from app.services.workflow.engine import _resolve_entity_type
    from app.domain.packs.definitions import TEMPLATE_TO_PACK
    record_orm = (
        _load_query(db, str(project_id))
        .filter(ProjectRecord.id == str(record_id))
        .first()
    )
    if not record_orm:
        raise HTTPException(status_code=404, detail="Record no encontrado")
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    entity_type = _resolve_entity_type(record_orm, pack_key)
    trans_cap = capability_for_transition(entity_type, body.action_id)
    if trans_cap:
        require_capability(ctx, trans_cap)

    needs_sprint, active_id = ensure_sprint_for_transition(
        db, project, record_orm, body.action_id, body.sprint_id,
    )
    if needs_sprint:
        raise_requires_sprint_assignment(record_orm, active_id)

    prev_status = record_orm.status
    effective_cascade = resolve_cascade_mode(
        cascade=body.cascade,
        cascade_mode=body.cascade_mode,
    )
    if effective_cascade != "none":
        apply_cascade_transition(
            db, project, record_orm, body.action_id, actor_id, ctx,
            cascade=effective_cascade,
        )
    else:
        assert_epic_done_allowed(db, project, record_orm, body.action_id)
        apply_transition(db, project, record_orm, body.action_id, actor_id, ctx)
    if body.action_id == "reabrir" and body.reopen_children:
        reopen_direct_done_children(db, record_orm, project)
    if body.action_id in ("cancel", "cancelar") and body.cancel_children == "all":
        cancel_all_descendants(db, record_orm, project, resolved_by=actor_id)
    if body.action_id == "devolver" and body.children_on_return != "unchanged":
        from app.services.scrum.return_children import apply_children_on_return

        apply_children_on_return(
            db, record_orm, project, body.children_on_return, resolved_by=actor_id,
        )
    write_audit(db, project=project, actor_id=actor_id,
                entity_type=record_orm.record_type, entity_id=record_orm.id,
                action="transitioned",
                changes={
                    "from": prev_status,
                    "to": record_orm.status,
                    "action": body.action_id,
                    "cascade": body.cascade,
                    "cascade_mode": body.cascade_mode,
                })
    db.commit()
    db.refresh(record_orm)
    return _to_response(db, record_orm)


@router.post("/{project_id}/records/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_project_records(
    project_id: str,
    body: ReorderRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    reorder_records(db, str(project_id), body.ordered_ids)


# ─── Blockers ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/records/{record_id}/blockers", response_model=list[BlockerResponse])
def list_record_blockers(
    project_id: str,
    record_id: str,
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    q = db.query(ProjectRecordBlocker).filter(
        ProjectRecordBlocker.record_id == str(record_id),
        ProjectRecordBlocker.project_id == str(project_id),
    )
    if not include_resolved:
        q = q.filter(ProjectRecordBlocker.resolved_at.is_(None))
    return [_blocker_to_response(b) for b in q.order_by(ProjectRecordBlocker.created_at).all()]


@router.get("/{project_id}/blockers", response_model=list[BlockerResponse])
def list_project_blockers(
    project_id: str,
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Lista todos los bloqueantes del proyecto (útil para BlockedView)."""
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    q = db.query(ProjectRecordBlocker).filter(
        ProjectRecordBlocker.project_id == str(project_id),
    )
    if not include_resolved:
        q = q.filter(ProjectRecordBlocker.resolved_at.is_(None))
    return [_blocker_to_response(b) for b in q.order_by(ProjectRecordBlocker.created_at).all()]


@router.post(
    "/{project_id}/records/{record_id}/blockers",
    response_model=BlockerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_blocker(
    project_id: str,
    record_id: str,
    body: CreateBlockerRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "blocker.create")
    project = get_project_or_404(db, project_id)
    record = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.id == str(record_id),
            ProjectRecord.project_id == str(project_id),
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record no encontrado")

    prev_status = record.status
    blocker = ProjectRecordBlocker(
        project_id=str(project_id),
        record_id=str(record_id),
        description=body.description,
        created_by=actor_id,
    )
    db.add(blocker)
    db.flush()
    sync_block_on_create(db, record)
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="blocker", entity_id=str(blocker.id), action="created",
        changes={
            "record_id": str(record_id),
            "description": body.description,
            "record_status": record.status,
            "record_status_before": prev_status,
        },
    )
    db.commit()
    db.refresh(blocker)
    return _blocker_to_response(blocker)


@router.post("/{project_id}/records/{record_id}/blockers/{blocker_id}/resolve", response_model=BlockerResponse)
def resolve_blocker(
    project_id: str,
    record_id: str,
    blocker_id: str,
    body: ResolveBlockerRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    project = get_project_or_404(db, project_id)
    blocker = db.query(ProjectRecordBlocker).filter(
        ProjectRecordBlocker.id == str(blocker_id),
        ProjectRecordBlocker.record_id == str(record_id),
        ProjectRecordBlocker.project_id == str(project_id),
    ).first()
    if not blocker:
        raise HTTPException(status_code=404, detail="Bloqueante no encontrado")
    if blocker.resolved_at is not None:
        raise HTTPException(status_code=409, detail="Bloqueante ya resuelto")
    record = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.id == str(record_id),
            ProjectRecord.project_id == str(project_id),
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record no encontrado")

    prev_status = record.status
    blocker.resolved_at = datetime.now(timezone.utc)
    blocker.resolved_by = actor_id
    blocker.resolution_note = body.resolution_note
    db.flush()
    sync_unblock_on_resolve(db, record)
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="blocker", entity_id=str(blocker.id), action="resolved",
        changes={
            "record_id": str(record_id),
            "record_status": record.status,
            "record_status_before": prev_status,
        },
    )
    db.commit()
    db.refresh(blocker)
    return _blocker_to_response(blocker)


# ─── Dependencies ─────────────────────────────────────────────────────────────

@router.get("/{project_id}/records/{record_id}/dependencies", response_model=DependenciesPayload)
def list_record_dependencies(
    project_id: str,
    record_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Devuelve predecesores y sucesores del record, ambos scoped al proyecto."""
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    predecessors = db.query(ProjectRecordDependency).filter(
        ProjectRecordDependency.successor_id == str(record_id),
        ProjectRecordDependency.project_id == str(project_id),
    ).all()
    successors = db.query(ProjectRecordDependency).filter(
        ProjectRecordDependency.predecessor_id == str(record_id),
        ProjectRecordDependency.project_id == str(project_id),
    ).all()
    return DependenciesPayload(
        predecessors=[_dep_to_response(d) for d in predecessors],
        successors=[_dep_to_response(d) for d in successors],
    )


@router.post("/{project_id}/dependencies", response_model=DependencyResponse, status_code=status.HTTP_201_CREATED)
def create_dependency(
    project_id: str,
    body: CreateDependencyRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "dependency.create")
    project = get_project_or_404(db, project_id)
    # Verify both records belong to this project
    for rid in (body.predecessor_id, body.successor_id):
        exists = db.query(ProjectRecord).filter(
            ProjectRecord.id == str(rid),
            ProjectRecord.project_id == str(project_id),
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Record {rid} no encontrado en el proyecto")
    dep = ProjectRecordDependency(
        project_id=str(project_id),
        predecessor_id=body.predecessor_id,
        successor_id=body.successor_id,
        created_by=actor_id,
    )
    db.add(dep)
    db.flush()
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="dependency", entity_id=str(dep.id), action="created",
        changes={"predecessor_id": body.predecessor_id, "successor_id": body.successor_id},
    )
    db.commit()
    db.refresh(dep)
    return _dep_to_response(dep)


@router.delete("/{project_id}/dependencies/{dep_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dependency(
    project_id: str,
    dep_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "dependency.delete")
    project = get_project_or_404(db, project_id)
    dep = db.query(ProjectRecordDependency).filter(
        ProjectRecordDependency.id == str(dep_id),
        ProjectRecordDependency.project_id == str(project_id),
    ).first()
    if not dep:
        raise HTTPException(status_code=404, detail="Dependencia no encontrada")
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="dependency", entity_id=str(dep.id), action="deleted",
        changes={"predecessor_id": dep.predecessor_id, "successor_id": dep.successor_id},
    )
    db.delete(dep)
    db.commit()

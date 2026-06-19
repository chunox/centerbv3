"""Registro de side-effects de workflow."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.audit import record_audit_log
from app.services.notifications import create_notification
from app.services.records.repository import (
    RecordEntityAdapter,
    _data,
    create_record,
    list_children,
    list_records,
    set_field,
    update_record_fields,
)
from app.services.workflow.capabilities import users_with_capability
from app.domain.records.types import RecordRef

SideEffectHandler = Callable[
    [
        Session,
        Project,
        Any,
        str,
        str,
        uuid.UUID,
        dict[str, Any],
        dict[str, Any] | None,
        dict[str, Any] | None,
    ],
    None,
]

_HANDLERS: dict[str, SideEffectHandler] = {}


def register_side_effect(effect_type: str, handler: SideEffectHandler) -> None:
    _HANDLERS[effect_type] = handler


def run_side_effect(
    db: Session,
    *,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None = None,
    side_effect_context: dict[str, Any] | None = None,
    entidad_tipo: str,
) -> None:
    etype = effect.get("type")
    if not etype:
        return
    handler = _HANDLERS.get(etype)
    if handler is None:
        return
    handler(
        db,
        project,
        entity,
        entity_type,
        action_id,
        actor_user_id,
        effect,
        form_data,
        side_effect_context,
        entidad_tipo,
    )


def _entity_id(entity: Any) -> uuid.UUID:
    return entity.id


def _report_parent_id(db: Session, entity: Any) -> uuid.UUID | None:
    if isinstance(entity, ProjectRecord):
        return entity.parent_id
    row = _record(db, entity)
    return row.parent_id


def _report_data(db: Session, entity: Any) -> dict[str, Any]:
    if isinstance(entity, ProjectRecord):
        return _data(entity)
    return _data(_record(db, entity))


def _set_report_generated_feature(
    db: Session, entity: Any, feature_id: uuid.UUID
) -> None:
    row = _record(db, entity)
    if row.record_type == "report":
        set_field(row, "generated_feature_id", str(feature_id))


def _record(db: Session, entity: Any) -> ProjectRecord:
    if isinstance(entity, ProjectRecord):
        return entity
    if hasattr(entity, "_record"):
        return entity._record
    if hasattr(entity, "record"):
        return entity.record
    row = db.get(ProjectRecord, entity.id)
    if row is not None:
        return row
    raise HTTPException(status_code=500, detail="Entidad sin registro asociado")


def _handle_notify(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    cap = effect.get("target", {}).get("capability")
    if cap:
        for uid in users_with_capability(db, project.id, cap):
            create_notification(
                db,
                user_id=uid,
                project_id=project.id,
                tipo="estado_changed",
                entidad_tipo=entidad_tipo,  # type: ignore[arg-type]
                entidad_id=_entity_id(entity),
            )


def _handle_notify_role(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    from app.services.workflow.capabilities import user_ids_with_role_slug

    role_slug = effect.get("target", {}).get("role_slug")
    if not role_slug:
        return
    for uid in user_ids_with_role_slug(db, project.id, role_slug):
        create_notification(
            db,
            user_id=uid,
            project_id=project.id,
            tipo="estado_changed",
            entidad_tipo=entidad_tipo,  # type: ignore[arg-type]
            entidad_id=_entity_id(entity),
        )


def _handle_set_field(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    field_key = effect.get("field_key")
    if not field_key:
        return
    row = _record(db, entity)
    value = effect.get("value")
    if value is None and effect.get("value_from_context") and side_effect_context:
        value = side_effect_context.get(effect["value_from_context"])
    if value is not None:
        set_field(row, field_key, str(value) if field_key == "sprint_id" else value)
        db.flush()
        if field_key == "sprint_id" and row.record_type == "feature":
            from app.services.scrum_effort import maybe_sync_scrum_on_sprint_assignment

            maybe_sync_scrum_on_sprint_assignment(db, project, row)


def _handle_clear_field(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    field_key = effect.get("field_key")
    if not field_key:
        return
    row = _record(db, entity)
    data = dict(row.data or {})
    data.pop(field_key, None)
    row.data = data
    db.flush()


def _handle_sync_scrum_sprint_dates(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    from app.services.scrum_effort import maybe_sync_scrum_on_sprint_assignment

    row = _record(db, entity)
    if row.record_type in ("feature", "task"):
        maybe_sync_scrum_on_sprint_assignment(db, project, row)


def _handle_reparent_to_sprint(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    raw = None
    if effect.get("value_from_context") and side_effect_context:
        raw = side_effect_context.get(effect["value_from_context"])
    if raw is None:
        return
    try:
        sprint_id = uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return
    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id:
        return
    row.parent_id = sprint_id
    db.flush()
    from app.services.scrum_effort import maybe_sync_scrum_on_sprint_assignment

    maybe_sync_scrum_on_sprint_assignment(db, project, row)
    from app.services.scrum_v2_structure import is_scrum_story, list_dev_tasks_for_story

    if is_scrum_story(row):
        for dev in list_dev_tasks_for_story(db, project.id, row.id):
            dev.parent_id = sprint_id
        db.flush()

    from app.services.scrum_metrics import sync_sprint_horas_planeadas

    sync_sprint_horas_planeadas(db, sprint, commit=False)


def _handle_reparent_to_backlog(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    from app.services.scrum_v2_structure import (
        ensure_product_backlog_record,
        is_scrum_story,
        is_sprint_record,
        list_dev_tasks_for_story,
    )

    row = _record(db, entity)
    previous_sprint_id = row.parent_id
    backlog = ensure_product_backlog_record(db, project, created_by=actor_user_id)
    row.parent_id = backlog.id
    db.flush()
    if is_scrum_story(row):
        for dev in list_dev_tasks_for_story(db, project.id, row.id):
            dev.parent_id = backlog.id
        db.flush()

    if previous_sprint_id is not None:
        previous_sprint = db.get(ProjectRecord, previous_sprint_id)
        if (
            previous_sprint is not None
            and previous_sprint.project_id == project.id
            and is_sprint_record(previous_sprint)
        ):
            from app.services.scrum_metrics import sync_sprint_horas_planeadas

            sync_sprint_horas_planeadas(db, previous_sprint, commit=False)


def _handle_finalize_parent_when_siblings_done(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if not row.parent_id:
        return
    target_state = effect.get("target_state", "finalizada")
    siblings = list_children(db, row.parent_id, row.record_type)
    if not siblings:
        return
    done_states = {"publicado", "descartado"}
    if not all(s.estado in done_states for s in siblings):
        return
    parent = db.get(ProjectRecord, row.parent_id)
    if parent is None or parent.estado == target_state:
        return
    from app.services.workflow.engine import apply_record_transition

    try:
        apply_record_transition(
            db,
            project=project,
            record=parent,
            action_id="finalizar",
            actor_user_id=actor_user_id,
        )
    except HTTPException:
        update_record_fields(db, parent, estado=target_state)
        db.flush()


def _handle_notify_reporter(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "report":
        return
    reported_by = uuid.UUID(_data(row).get("reported_by") or str(row.created_by))
    create_notification(
        db,
        user_id=reported_by,
        project_id=project.id,
        tipo=effect.get("notification_tipo", "reporte_resuelto"),
        entidad_tipo="feature_report",
        entidad_id=row.id,
    )


def _handle_generate_feature_from_report(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "report":
        return
    report_id = row.id
    parent_id = row.parent_id
    report_tipo = _data(row).get("tipo", "bug")
    ctx = side_effect_context or {}
    milestone_id = ctx.get("milestone_id")
    if milestone_id is None:
        parent_feature = db.get(ProjectRecord, parent_id)
        if parent_feature and parent_feature.parent_id:
            milestone_id = parent_feature.parent_id
    if milestone_id is None:
        raise HTTPException(status_code=500, detail="milestone_id requerido")
    original = db.get(ProjectRecord, parent_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Feature original no encontrada")
    fd = form_data or ctx.get("form_data") or {}
    nombre = fd.get("nombre_feature") or f"Fix: {original.titulo}"
    tipo = report_tipo or "bug"
    data: dict[str, Any] = {
        "tipo": tipo,
        "prioridad": "media",
        "origen_report_id": str(report_id),
        "origen_feature_id": str(original.id),
    }
    if tipo == "mejora" and fd.get("duracion_estimada"):
        data["duracion_estimada"] = int(fd["duracion_estimada"])
    new_feature = create_record(
        db,
        project,
        entity_type="feature",
        titulo=nombre,
        created_by=actor_user_id,
        parent_id=milestone_id,
        data=data,
        fecha_inicio=original.fecha_inicio,
        fecha_fin=original.fecha_fin,
    )
    _set_report_generated_feature(db, entity, new_feature.id)
    if tipo == "mejora" and fd.get("duracion_estimada"):
        milestone = db.get(ProjectRecord, milestone_id)
        if milestone is not None and milestone.fecha_fin is not None:
            update_record_fields(
                db,
                milestone,
                fecha_fin=milestone.fecha_fin
                + timedelta(days=int(fd["duracion_estimada"])),
            )
    from app.services.features import ensure_default_task

    ensure_default_task(db, new_feature, created_by=actor_user_id)


def _handle_sync_milestone_from_report(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "report":
        return
    parent_id = row.parent_id
    ctx = side_effect_context or {}
    milestone_id = ctx.get("milestone_id")
    if milestone_id is None:
        feature = db.get(ProjectRecord, parent_id)
        milestone_id = feature.parent_id if feature else None
    if milestone_id is not None:
        milestone = db.get(ProjectRecord, milestone_id)
        if milestone is not None:
            from app.services.milestones import sync_milestone_state

            sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)


def _cancel_record_cascade(
    db: Session,
    project: Project,
    record: ProjectRecord,
    actor_user_id: uuid.UUID,
) -> None:
    if record.estado == "cancelado" or record.estado == "cancel":
        return
    action = "cancelar" if record.record_type == "feature" else "cancel"
    try:
        from app.services.workflow.engine import apply_record_transition

        apply_record_transition(
            db,
            project,
            record,
            record_ref=RecordRef(
                id=record.id,
                record_type=record.record_type,
                project_id=project.id,
            ),
            action_id=action,
            actor_user_id=actor_user_id,
        )
    except HTTPException:
        update_record_fields(db, record, estado="cancelado" if record.record_type != "task" else "cancel")


def _handle_cancel_stories_cascade(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    from app.services.scrum_v2_structure import is_sprint_record, list_stories_for_sprint

    row = _record(db, entity)
    if not is_sprint_record(row):
        return
    for story in list_stories_for_sprint(db, row.project_id, row.id):
        _cancel_record_cascade(db, project, story, actor_user_id)


def _handle_cancel_features_cascade(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "milestone":
        return
    for feature in list_children(db, row.id, "feature"):
        _cancel_record_cascade(db, project, feature, actor_user_id)


def _handle_cancel_tasks_cascade(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "feature":
        return
    for task in list_children(db, row.id, "task"):
        if task.estado != "cancel":
            update_record_fields(db, task, estado="cancel")
            record_audit_log(
                db,
                project_id=project.id,
                user_id=actor_user_id,
                entidad_tipo="tarea",
                entidad_id=task.id,
                accion="estado_changed",
                campo="estado",
                valor_anterior=task.estado,
                valor_nuevo="cancel",
            )


def _handle_sync_tasks(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "feature" or effect.get("rule") != "complete_ready_for_test":
        return
    from app.services.workflow.categories import (
        resolve_workflow,
        task_done_state_keys,
        task_test_state_keys,
    )

    task_wf = resolve_workflow(db, project.id, "task", project.template_slug or "default")
    test_keys = task_test_state_keys(task_wf)
    done_to = next(iter(task_done_state_keys(task_wf)), "completed")
    for task in list_children(db, row.id, "task"):
        if task.estado in test_keys:
            prev = task.estado
            update_record_fields(db, task, estado=done_to)
            record_audit_log(
                db,
                project_id=project.id,
                user_id=actor_user_id,
                entidad_tipo="tarea",
                entidad_id=task.id,
                accion="estado_changed",
                campo="estado",
                valor_anterior=prev,
                valor_nuevo="completed (workflow)",
            )


def _handle_rework_tasks(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    if row.record_type != "feature":
        return
    from app.services.workflow.categories import (
        resolve_workflow,
        state_keys_in_categories,
        task_test_state_keys,
    )

    task_wf = resolve_workflow(db, project.id, "task", project.template_slug or "default")
    test_keys = task_test_state_keys(task_wf)
    active_keys = state_keys_in_categories(task_wf, frozenset({"active"}))
    rework_to = next(iter(active_keys), "in_progress")
    for task in list_children(db, row.id, "task"):
        if task.estado in test_keys:
            prev = task.estado
            update_record_fields(db, task, estado=rework_to)
            record_audit_log(
                db,
                project_id=project.id,
                user_id=actor_user_id,
                entidad_tipo="tarea",
                entidad_id=task.id,
                accion="estado_changed",
                campo="estado",
                valor_anterior=prev,
                valor_nuevo="in_progress (workflow_rework)",
            )


def _resolve_parent_id(row: ProjectRecord, parent_mode: str) -> uuid.UUID | None:
    if parent_mode == "entity":
        return row.id
    if parent_mode == "parent":
        return row.parent_id
    if parent_mode == "milestone":
        if row.parent_id is None:
            return None
        parent = row.parent_id
        return parent
    return row.parent_id


def _handle_create_record(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    row = _record(db, entity)
    target = effect.get("target") or {}
    record_type = target.get("record_type")
    if not record_type:
        return
    parent_mode = target.get("parent", "entity")
    parent_id = _resolve_parent_id(row, parent_mode)
    if parent_mode == "milestone" and parent_id is not None:
        parent_row = db.get(ProjectRecord, parent_id)
        if parent_row is not None and parent_row.parent_id is not None:
            parent_id = parent_row.parent_id
    titulo = target.get("titulo") or f"Nuevo {record_type}"
    if isinstance(titulo, str):
        titulo = _interpolate_template(db, titulo, row, form_data)
    data = dict(target.get("data") or {})
    initial_state = target.get("initial_state")
    created = create_record(
        db,
        project,
        entity_type=record_type,
        titulo=str(titulo),
        created_by=actor_user_id,
        parent_id=parent_id,
        data=data,
    )
    if initial_state:
        update_record_fields(db, created, estado=str(initial_state))
        db.flush()
    if record_type == "feature":
        from app.services.features import ensure_default_task

        ensure_default_task(db, created, created_by=actor_user_id)


def _interpolate_template(
    db: Session,
    value: str,
    row: ProjectRecord,
    form_data: dict | None,
) -> str:
    fd = form_data or {}
    parent_title = ""
    if row.parent_id:
        parent_row = db.get(ProjectRecord, row.parent_id)
        if parent_row:
            parent_title = parent_row.titulo or ""
    replacements = {
        "{parent.title}": parent_title,
        "{parent_title}": parent_title,
        "{entity_titulo}": row.titulo or "",
        "{title}": row.titulo or "",
        "{entity_type}": row.record_type,
    }
    out = value
    for key, repl in replacements.items():
        out = out.replace(key, repl)
    if "{" in out:
        try:
            out = out.format(entity_titulo=row.titulo, entity_type=row.record_type, **fd)
        except (KeyError, ValueError):
            pass
    return out


def _handle_run_transition(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    from app.services.workflow.engine import apply_entity_transition

    row = _record(db, entity)
    target_mode = effect.get("target", "parent")
    target_action = effect.get("action_id")
    if not target_action:
        return
    target_row = row
    if target_mode == "parent" and row.parent_id:
        target_row = db.get(ProjectRecord, row.parent_id)
    elif target_mode == "sibling" and row.parent_id:
        siblings = list_children(db, row.parent_id, effect.get("entity_type") or row.record_type)
        target_row = siblings[0] if siblings else row
    if target_row is None:
        return
    apply_entity_transition(
        db,
        project,
        target_row,
        entity_type=target_row.record_type,
        action_id=target_action,
        actor_user_id=actor_user_id,
        form_data=form_data,
    )


register_side_effect("notify", _handle_notify)
register_side_effect("notify_role", _handle_notify_role)
register_side_effect("set_field", _handle_set_field)
register_side_effect("clear_field", _handle_clear_field)
register_side_effect("sync_scrum_sprint_dates", _handle_sync_scrum_sprint_dates)
register_side_effect("reparent_to_sprint", _handle_reparent_to_sprint)
register_side_effect("reparent_to_backlog", _handle_reparent_to_backlog)
register_side_effect("finalize_parent_when_siblings_done", _handle_finalize_parent_when_siblings_done)
register_side_effect("notify_reporter", _handle_notify_reporter)
register_side_effect("generate_feature_from_report", _handle_generate_feature_from_report)
register_side_effect("sync_milestone_from_report", _handle_sync_milestone_from_report)
register_side_effect("cancel_features_cascade", _handle_cancel_features_cascade)
register_side_effect("cancel_stories_cascade", _handle_cancel_stories_cascade)
register_side_effect("cancel_tasks_cascade", _handle_cancel_tasks_cascade)
register_side_effect("sync_tasks", _handle_sync_tasks)
register_side_effect("rework_tasks", _handle_rework_tasks)
register_side_effect("create_record", _handle_create_record)
register_side_effect("run_transition", _handle_run_transition)

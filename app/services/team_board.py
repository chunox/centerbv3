"""Agregación de asignaciones por miembro para vista Equipo PM."""
from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import Project, ProjectMember, ProjectRecord, ProjectRecordType, User
from app.schemas.team_board import (
    TeamAssignableTypeRead,
    TeamAssignmentRead,
    TeamBoardRead,
    TeamBoardTotalsRead,
    TeamFeatureScheduleRead,
    TeamMemberBoardRead,
    TeamMemberSummaryRead,
)
from app.services.project_profile import legacy_tipo_for_project
from app.services.records.repository import list_assignee_ids
from app.services.workflow.categories import (
    batch_load_workflows,
    is_terminal_state,
    resolve_workflow,
    state_category,
    state_meta,
)

_ACTIVE_CATEGORIES = frozenset({"backlog", "todo", "draft", "active", "test", "pending", "inbox"})
_DONE_CATEGORIES = frozenset({"done"})


def _resolve_routes(pack_slug: str, record_type: str) -> tuple[str | None, str | None]:
    pack = pack_slug or "software"
    if pack == "marketing360" and record_type == "pieza":
        return "board", "v/board"
    if record_type == "task":
        return "kanban", "kanban"
    if record_type in ("tarea", "entregable"):
        return "board", "board"
    return "board", "board"


def _classify_item(category: str | None, is_terminal: bool) -> str:
    if is_terminal and category != "done":
        return "terminal"
    if category in _DONE_CATEGORIES or (is_terminal and category == "done"):
        return "done"
    if category in _ACTIVE_CATEGORIES or (category is None and not is_terminal):
        return "active"
    if is_terminal:
        return "terminal"
    return "active"


def _assignable_types(db: Session, project_id: UUID) -> list[ProjectRecordType]:
    rows = list(
        db.scalars(
            select(ProjectRecordType)
            .where(ProjectRecordType.project_id == project_id)
            .order_by(ProjectRecordType.orden.asc())
        )
    )
    return [rt for rt in rows if isinstance(rt.traits, dict) and rt.traits.get("assignees")]


def _load_parent_chain(
    db: Session,
    parent_ids: set[UUID],
) -> tuple[dict[UUID, ProjectRecord], dict[UUID, str]]:
    parent_by_id: dict[UUID, ProjectRecord] = {}
    if parent_ids:
        for parent in db.scalars(
            select(ProjectRecord).where(ProjectRecord.id.in_(parent_ids))
        ):
            parent_by_id[parent.id] = parent

    root_parent_ids = {p.parent_id for p in parent_by_id.values() if p.parent_id}
    root_parent_titles: dict[UUID, str] = {}
    if root_parent_ids:
        for root in db.scalars(
            select(ProjectRecord).where(ProjectRecord.id.in_(root_parent_ids))
        ):
            root_parent_titles[root.id] = root.titulo

    return parent_by_id, root_parent_titles


def _build_feature_schedules(
    parent_by_id: dict[UUID, ProjectRecord],
    root_parent_titles: dict[UUID, str],
    all_items: list[TeamAssignmentRead],
    members: list[TeamMemberBoardRead],
) -> list[TeamFeatureScheduleRead]:
    by_parent: dict[UUID, list[TeamAssignmentRead]] = defaultdict(list)
    for item in all_items:
        if item.parent_id:
            by_parent[item.parent_id].append(item)

    assignees_by_record: dict[UUID, list[str]] = defaultdict(list)
    for member in members:
        for item in member.items:
            assignees_by_record[item.record_id].append(member.nombre)

    schedules: list[TeamFeatureScheduleRead] = []
    for parent_id, items in by_parent.items():
        parent = parent_by_id.get(parent_id)
        if parent is None:
            continue
        assignee_names = sorted(
            {
                name
                for item in items
                for name in assignees_by_record.get(item.record_id, [])
            }
        )
        active_tasks = sum(
            1
            for item in items
            if _classify_item(item.category, item.is_terminal) == "active"
        )
        root_id = parent.parent_id
        schedules.append(
            TeamFeatureScheduleRead(
                feature_id=parent.id,
                titulo=parent.titulo,
                root_parent_titulo=root_parent_titles.get(root_id) if root_id else None,
                fecha_inicio=parent.fecha_inicio,
                fecha_fin=parent.fecha_fin,
                active_tasks=active_tasks,
                assignee_names=assignee_names,
            )
        )

    return sorted(
        schedules,
        key=lambda row: (
            (row.root_parent_titulo or "").lower(),
            row.titulo.lower(),
        ),
    )


def _assignment_item(
    *,
    db: Session,
    record: ProjectRecord,
    type_labels: dict[str, str],
    workflows: dict,
    project: Project,
    project_tipo: str,
    pack_slug: str,
    parent_by_id: dict[UUID, ProjectRecord],
    root_parent_titles: dict[UUID, str],
    stamp_project: bool,
) -> TeamAssignmentRead:
    wf = workflows.get((project.id, record.record_type))
    if wf is None:
        wf = resolve_workflow(db, project.id, record.record_type, project_tipo)
    meta = state_meta(wf, record.estado)
    cat = state_category(wf, record.estado)
    terminal = is_terminal_state(wf, record.estado)
    wb_route, view_route = _resolve_routes(pack_slug, record.record_type)

    parent = parent_by_id.get(record.parent_id) if record.parent_id else None
    root_parent_id = parent.parent_id if parent else None

    return TeamAssignmentRead(
        record_id=record.id,
        record_type=record.record_type,
        record_type_label=type_labels.get(record.record_type, record.record_type),
        titulo=record.titulo,
        estado=record.estado,
        estado_label=meta["label"],
        badge=meta["badge"],
        category=cat,
        is_terminal=terminal,
        parent_id=record.parent_id,
        parent_titulo=parent.titulo if parent else None,
        root_parent_id=root_parent_id,
        root_parent_titulo=root_parent_titles.get(root_parent_id) if root_parent_id else None,
        project_id=project.id if stamp_project else None,
        project_nombre=project.nombre if stamp_project else None,
        fecha_inicio=record.fecha_inicio,
        fecha_fin=record.fecha_fin,
        updated_at=record.updated_at,
        workbench_route=wb_route,
        view_route=view_route,
    )


def build_team_board(db: Session, project: Project, *, stamp_project: bool = False) -> TeamBoardRead:
    assignable_rows = _assignable_types(db, project.id)
    assignable_types = [
        TeamAssignableTypeRead(key=rt.key, label=rt.label or rt.key) for rt in assignable_rows
    ]
    assignable_keys = [rt.key for rt in assignable_rows]
    type_labels = {rt.key: rt.label or rt.key for rt in assignable_rows}

    workflows = batch_load_workflows(db, [project])
    project_tipo = legacy_tipo_for_project(project)
    pack_slug = project.pack_slug or "software"

    items_by_user: dict[UUID, list[TeamAssignmentRead]] = defaultdict(list)
    unassigned: list[TeamAssignmentRead] = []
    all_items: list[TeamAssignmentRead] = []
    parent_by_id: dict[UUID, ProjectRecord] = {}
    root_parent_titles: dict[UUID, str] = {}

    if assignable_keys:
        records = list(
            db.scalars(
                select(ProjectRecord)
                .options(joinedload(ProjectRecord.assignees))
                .where(
                    ProjectRecord.project_id == project.id,
                    ProjectRecord.record_type.in_(assignable_keys),
                )
                .order_by(ProjectRecord.updated_at.desc(), ProjectRecord.titulo.asc())
            ).unique()
        )

        parent_ids = {r.parent_id for r in records if r.parent_id}
        parent_by_id, root_parent_titles = _load_parent_chain(db, parent_ids)

        for record in records:
            item = _assignment_item(
                db=db,
                record=record,
                type_labels=type_labels,
                workflows=workflows,
                project=project,
                project_tipo=project_tipo,
                pack_slug=pack_slug,
                parent_by_id=parent_by_id,
                root_parent_titles=root_parent_titles,
                stamp_project=stamp_project,
            )
            all_items.append(item)

            assignee_ids = list_assignee_ids(db, record)
            if not assignee_ids:
                unassigned.append(item)
            else:
                for uid in assignee_ids:
                    items_by_user[uid].append(item)

    member_rows = list(
        db.scalars(
            select(ProjectMember)
            .options(joinedload(ProjectMember.role), joinedload(ProjectMember.user))
            .where(ProjectMember.project_id == project.id)
            .order_by(ProjectMember.joined_at.asc())
        )
    )

    users_by_id: dict[UUID, User] = {}
    for m in member_rows:
        if m.user_id not in users_by_id and m.user is not None:
            users_by_id[m.user_id] = m.user

    grouped: dict[UUID, TeamMemberBoardRead] = {}
    for m in member_rows:
        user = users_by_id.get(m.user_id)
        nombre = user.nombre if user else "Usuario"
        email = user.email if user else None
        slug = m.role.slug if m.role else ""
        label = m.role.nombre if m.role else slug

        if m.user_id not in grouped:
            grouped[m.user_id] = TeamMemberBoardRead(
                user_id=m.user_id,
                nombre=nombre,
                email=email,
                role_slugs=[],
                role_labels=[],
                items=items_by_user.get(m.user_id, []),
            )
        row = grouped[m.user_id]
        if slug and slug not in row.role_slugs:
            row.role_slugs.append(slug)
        if label and label not in row.role_labels:
            row.role_labels.append(label)

    for member in grouped.values():
        summary = TeamMemberSummaryRead()
        for item in member.items:
            summary.total += 1
            bucket = _classify_item(item.category, item.is_terminal)
            if bucket == "done":
                summary.done += 1
            elif bucket == "terminal":
                summary.terminal += 1
            else:
                summary.active += 1
        member.summary = summary

    members = sorted(grouped.values(), key=lambda m: m.nombre.lower())
    feature_schedules = _build_feature_schedules(
        parent_by_id, root_parent_titles, all_items, members
    )

    totals = TeamBoardTotalsRead(
        members=len(members),
        assignments=len(all_items),
        unassigned=len(unassigned),
    )
    for item in all_items:
        bucket = _classify_item(item.category, item.is_terminal)
        if bucket == "done":
            totals.done += 1
        elif bucket != "terminal":
            totals.active += 1

    return TeamBoardRead(
        assignable_types=assignable_types,
        members=members,
        unassigned=unassigned,
        feature_schedules=feature_schedules,
        totals=totals,
    )

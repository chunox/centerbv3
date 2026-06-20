"""Validación de invariantes v2 para seed demo Scrum (t6/t7)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Project, ProjectRecord
from app.services.scrum_metrics import (
    compute_sprint_completed_horas,
    sum_sprint_committed_horas,
)
from app.services.scrum_tasks import STORY_SYNC_FROZEN
from app.services.scrum_v2_structure import (
    get_product_backlog_record,
    get_scrum_role,
    is_scrum_dev_task,
    is_scrum_epic_task,
    is_scrum_story,
    is_sprint_record,
    list_all_dev_tasks_for_story,
    list_dev_tasks_for_story,
    list_epic_tasks,
    list_stories_for_sprint,
    list_stories_in_backlog,
)

HOURS_TOLERANCE = 0.15

T6_TEMPLATE = "t6_scrum_interno"
T7_TEMPLATE = "t7_scrum_cliente"

# Estados esperados por título de historia (post-seed canónico)
T6_SPRINT_STORY_STATES: dict[int, dict[str, str]] = {
    1: {titulo: estado for titulo, _, _, estado, _ in [
        ("Modelo de almacenes y SKUs", "8", "alta", "completado", [4, 4, 2]),
        ("API CRUD inventario", "5", "alta", "completado", [3, 3, 2]),
        ("UI: lista de stock con filtros", "5", "alta", "completado", [3, 2, 2]),
        ("Importación masiva CSV de productos", "3", "media", "completado", [2, 2]),
        ("Tests integración capa repositorio", "3", "media", "completado", [2, 1]),
        ("Documentación API inventario (OpenAPI)", "2", "baja", "completado", [1, 1]),
    ]},
    2: {titulo: estado for titulo, _, _, estado, _ in [
        ("Recepción de mercadería con lote", "8", "alta", "en_progreso", [3, 3, 2]),
        ("Movimientos entre almacenes", "5", "alta", "en_progreso", [2.5, 2.5, 1.5]),
        ("Alertas de stock mínimo por SKU", "5", "media", "en_progreso", [2, 2, 1.5]),
        ("Historial de movimientos auditables", "3", "media", "en_progreso", [2, 1.5]),
        ("Reserva de stock para pedidos", "5", "alta", "pendiente", [2.5, 2.5]),
        ("UI: panel de operaciones diarias", "3", "media", "pendiente", [1.5, 1]),
    ]},
    3: {titulo: estado for titulo, _, _, estado, _ in [
        ("Estados de envío y timeline", "8", "alta", "pendiente", [4, 4, 2]),
        ("Tracking por código de seguimiento", "5", "alta", "pendiente", [3, 3]),
        ("Notificaciones email en hitos clave", "5", "media", "pendiente", [2.5, 2.5]),
        ("Webhook para integraciones TMS", "3", "media", "pendiente", [2, 2]),
        ("Mapa de rutas activas (vista lista)", "3", "baja", "pendiente", [2, 1]),
    ]},
    4: {titulo: estado for titulo, _, _, estado, _ in [
        ("Dashboard rotación de inventario", "8", "alta", "pendiente", [3, 3]),
        ("SLA de entrega por carrier", "5", "alta", "pendiente", [3, 3]),
        ("Export CSV de métricas semanales", "3", "media", "pendiente", [3, 3]),
        ("Gráficos de incidencias por hub", "5", "media", "pendiente", [3, 3]),
        ("Reporte de fill-rate por almacén", "3", "baja", "pendiente", [3, 3]),
    ]},
}

SCRUM_STORY_ALLOWED_STATES = frozenset(
    {
        "product_backlog",
        "planificado",
        "pendiente",
        "en_progreso",
        "completado",
        "cancelado",
    }
)

SCRUM_LEGACY_UAT_STATES = frozenset(
    {"uat", "esperando_liberacion_pm", "esperando_validacion_cliente"}
)

T7_SPRINT_STORY_STATES: dict[int, dict[str, str]] = {
    1: {
        "Pagina de catalogo con grilla de productos": "completado",
        "Filtros por categoria, precio y disponibilidad": "completado",
        "Pagina de detalle de producto con galeria": "completado",
        "Busqueda por nombre y descripcion": "completado",
    },
    2: {
        "Carrito persistente (localStorage + API)": "en_progreso",
        "Checkout: datos de envio y resumen": "en_progreso",
        "Integracion con pasarela de pago (Stripe)": "en_progreso",
        "Pagina de confirmacion y email transaccional": "en_progreso",
        "Validaciones de stock en checkout": "pendiente",
    },
    3: {
        "Historial de pedidos con filtros": "pendiente",
        "Estado de pedido en tiempo real (polling)": "pendiente",
        "Gestion de direcciones de envio": "pendiente",
        "Descarga de factura en PDF": "pendiente",
    },
}


@dataclass
class ValidationIssue:
    check: str
    message: str
    severity: str = "error"


@dataclass
class ProjectValidationResult:
    project_id: uuid.UUID
    template_slug: str
    nombre: str
    issues: list[ValidationIssue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


@dataclass
class ScrumSeedValidationReport:
    results: list[ProjectValidationResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "projects": [
                {
                    "project_id": str(r.project_id),
                    "template_slug": r.template_slug,
                    "nombre": r.nombre,
                    "ok": r.ok,
                    "counts": r.counts,
                    "issues": [
                        {"check": i.check, "message": i.message, "severity": i.severity}
                        for i in r.issues
                    ],
                }
                for r in self.results
            ],
        }


def find_project_by_template(
    db: Session,
    template_slug: str,
    *,
    nombre: str | None = None,
) -> Project | None:
    stmt = select(Project).where(Project.template_slug == template_slug)
    if nombre:
        stmt = stmt.where(Project.nombre == nombre)
    stmt = stmt.order_by(Project.created_at.desc())
    return db.scalar(stmt)


def _issue(
    result: ProjectValidationResult,
    check: str,
    message: str,
    *,
    severity: str = "error",
) -> None:
    result.issues.append(ValidationIssue(check=check, message=message, severity=severity))


def _hours_close(a: float, b: float) -> bool:
    return abs(a - b) <= HOURS_TOLERANCE


def _all_scrum_tasks(db: Session, project_id: uuid.UUID) -> list[ProjectRecord]:
    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
            )
        )
    )
    return [r for r in rows if get_scrum_role(r) in ("epic", "story", "dev")]


def _dev_parent_is_story(dev: ProjectRecord, db: Session) -> bool:
    data = dev.data if isinstance(dev.data, dict) else {}
    parent_key = str(data.get("parent_task_id") or "")
    if not parent_key:
        return False
    try:
        parent = db.get(ProjectRecord, uuid.UUID(parent_key))
    except (TypeError, ValueError):
        return False
    return parent is not None and is_scrum_story(parent)


def validate_project_scrum_seed(
    db: Session,
    project: Project,
    *,
    expected_epics: int,
    expected_sprints: int,
    expected_backlog_stories: int,
    expected_sprint_story_counts: dict[int, int],
    sprint_story_states: dict[int, dict[str, str]] | None = None,
    forbid_legacy_uat_states: bool = False,
    blocked_story_titles: frozenset[str] = frozenset(),
) -> ProjectValidationResult:
    result = ProjectValidationResult(
        project_id=project.id,
        template_slug=project.template_slug,
        nombre=project.nombre,
    )
    backlog = get_product_backlog_record(db, project.id)
    if backlog is None:
        _issue(result, "product_backlog", "Product backlog record no encontrado")
        return result

    epics = list_epic_tasks(db, project.id)
    sprints = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "sprint",
            ).order_by(ProjectRecord.orden.asc())
        )
    )
    sprints = [s for s in sprints if is_sprint_record(s)]
    backlog_stories = list_stories_in_backlog(db, project.id)
    all_tasks = _all_scrum_tasks(db, project.id)
    dev_tasks = [t for t in all_tasks if is_scrum_dev_task(t)]
    stories = [t for t in all_tasks if is_scrum_story(t)]

    result.counts = {
        "epics": len(epics),
        "sprints": len(sprints),
        "backlog_stories": len(backlog_stories),
        "sprint_stories": sum(
            len(list_stories_for_sprint(db, project.id, s.id)) for s in sprints
        ),
        "dev_tasks": len(dev_tasks),
        "nested_dev_tasks": 0,
    }

    if len(epics) != expected_epics:
        _issue(result, "counts.epics", f"esperadas {expected_epics}, hay {len(epics)}")
    if len(sprints) != expected_sprints:
        _issue(result, "counts.sprints", f"esperados {expected_sprints}, hay {len(sprints)}")
    if len(backlog_stories) != expected_backlog_stories:
        _issue(
            result,
            "counts.backlog",
            f"esperadas {expected_backlog_stories}, hay {len(backlog_stories)}",
        )

    for sprint in sprints:
        orden = sprint.orden or 0
        sprint_stories = list_stories_for_sprint(db, project.id, sprint.id)
        expected_count = expected_sprint_story_counts.get(orden)
        if expected_count is not None and len(sprint_stories) != expected_count:
            _issue(
                result,
                f"counts.sprint_{orden}",
                f"esperadas {expected_count} historias, hay {len(sprint_stories)}",
            )

        committed = sum_sprint_committed_horas(db, project.id, sprint.id)
        data = sprint.data or {}
        stored_planned = data.get("horas_planeadas")
        try:
            planned_val = float(stored_planned) if stored_planned is not None else None
        except (TypeError, ValueError):
            planned_val = None
        if planned_val is None:
            _issue(
                result,
                f"sprint_{orden}.horas_planeadas",
                "horas_planeadas no persistidas en sprint.data",
            )
        elif not _hours_close(planned_val, committed):
            _issue(
                result,
                f"sprint_{orden}.horas_planeadas",
                f"horas_planeadas={planned_val} != rollup={committed}",
            )

        if sprint.estado == "completado":
            completed = compute_sprint_completed_horas(db, project.id, sprint.id)
            try:
                stored_done = float(data.get("horas_completadas") or 0)
            except (TypeError, ValueError):
                stored_done = -1.0
            if not _hours_close(stored_done, completed):
                _issue(
                    result,
                    f"sprint_{orden}.horas_completadas",
                    f"horas_completadas={stored_done} != rollup={completed}",
                )

        if sprint.orden == 1 and sprint.estado == "completado" and project.template_slug == T6_TEMPLATE:
            for story in sprint_stories:
                if story.estado != "completado":
                    continue
                logs = list(
                    db.scalars(
                        select(AuditLog).where(
                            AuditLog.project_id == project.id,
                            AuditLog.entidad_id == story.id,
                            AuditLog.campo == "estado",
                            AuditLog.valor_nuevo.like("completado%"),
                        )
                    )
                )
                if not logs:
                    _issue(
                        result,
                        "burndown.audit",
                        f"sin audit completado para historia S1: {story.titulo}",
                    )

    for epic in epics:
        if epic.parent_id != backlog.id:
            _issue(
                result,
                "hierarchy.epic",
                f"épica {epic.titulo!r} parent_id != product_backlog",
            )

    for story in stories:
        data = story.data if isinstance(story.data, dict) else {}
        epic_raw = data.get("epic_task_id")
        if not epic_raw:
            _issue(result, "hierarchy.story", f"historia {story.titulo!r} sin epic_task_id")
        else:
            epic = db.get(ProjectRecord, uuid.UUID(str(epic_raw)))
            if epic is None or epic.project_id != project.id or not is_scrum_epic_task(epic):
                _issue(
                    result,
                    "hierarchy.story",
                    f"historia {story.titulo!r} epic_task_id inválido",
                )

        legacy_sprint = data.get("sprint_id")
        if legacy_sprint not in (None, ""):
            _issue(
                result,
                "legacy.sprint_id",
                f"historia {story.titulo!r} tiene data.sprint_id legacy={legacy_sprint!r}",
            )

        in_backlog = story.parent_id == backlog.id
        if in_backlog:
            if story.estado != "product_backlog":
                _issue(
                    result,
                    "hierarchy.backlog_story",
                    f"historia backlog {story.titulo!r} estado={story.estado!r}",
                )
        else:
            parent = db.get(ProjectRecord, story.parent_id) if story.parent_id else None
            if parent is None or not is_sprint_record(parent):
                _issue(
                    result,
                    "hierarchy.committed_story",
                    f"historia {story.titulo!r} parent_id no es sprint",
                )
            elif story.estado == "product_backlog":
                _issue(
                    result,
                    "hierarchy.committed_story",
                    f"historia en sprint {story.titulo!r} aún en product_backlog",
                )

        if story.estado not in SCRUM_STORY_ALLOWED_STATES:
            _issue(
                result,
                "workflow.state",
                f"historia {story.titulo!r} en estado legacy/no permitido: {story.estado!r}",
            )

        if forbid_legacy_uat_states and story.estado in SCRUM_LEGACY_UAT_STATES:
            _issue(
                result,
                "workflow.template",
                f"historia con estado UAT/PM legacy: {story.titulo!r}={story.estado!r}",
            )

        if story.titulo in blocked_story_titles:
            if not data.get("bloqueada"):
                _issue(result, "blocked", f"historia {story.titulo!r} debería estar bloqueada")

        direct_devs = list_dev_tasks_for_story(db, project.id, story.id)
        story_devs = list_all_dev_tasks_for_story(db, project.id, story.id)
        for dev in direct_devs:
            if dev.parent_id != story.parent_id:
                _issue(
                    result,
                    "hierarchy.dev",
                    f"dev {dev.titulo!r} parent_id != story.parent_id",
                )
            dev_data = dev.data if isinstance(dev.data, dict) else {}
            if str(dev_data.get("parent_task_id") or "") != str(story.id):
                _issue(
                    result,
                    "hierarchy.dev",
                    f"dev {dev.titulo!r} parent_task_id != story.id",
                )

        if story.estado == "completado" and story_devs:
            from app.services.scrum_tasks import resolve_workflow_for_record
            from app.services.workflow.categories import task_done_state_keys

            task_wf = resolve_workflow_for_record(db, project, story_devs[0])
            done_keys = task_done_state_keys(task_wf) if task_wf else frozenset({"completed"})
            open_devs = [d for d in story_devs if d.estado not in done_keys]
            if open_devs:
                states = ", ".join(f"{d.titulo!r}={d.estado!r}" for d in open_devs)
                _issue(
                    result,
                    "sync.dev_done",
                    f"historia completada {story.titulo!r} con dev tasks abiertas: {states}",
                    severity="warning",
                )

    for dev in dev_tasks:
        if _dev_parent_is_story(dev, db):
            continue
        result.counts["nested_dev_tasks"] += 1

    if sprint_story_states:
        for sprint in sprints:
            orden = sprint.orden or 0
            expected_by_title = sprint_story_states.get(orden)
            if not expected_by_title:
                continue
            for story in list_stories_for_sprint(db, project.id, sprint.id):
                expected_state = expected_by_title.get(story.titulo or "")
                if expected_state and story.estado != expected_state:
                    _issue(
                        result,
                        f"state.sprint_{orden}",
                        f"{story.titulo!r}: esperado {expected_state!r}, actual {story.estado!r}",
                    )

    return result


def validate_demo_scrum_seed(db: Session) -> ScrumSeedValidationReport:
    report = ScrumSeedValidationReport()
    t6 = find_project_by_template(db, T6_TEMPLATE, nombre="Logistics Hub")
    t7 = find_project_by_template(db, T7_TEMPLATE, nombre="E-commerce Relaunch")
    if t6 is None:
        report.results.append(
            ProjectValidationResult(
                project_id=uuid.UUID(int=0),
                template_slug=T6_TEMPLATE,
                nombre="(missing)",
                issues=[ValidationIssue("project", f"Proyecto {T6_TEMPLATE} no encontrado")],
            )
        )
    else:
        report.results.append(
            validate_project_scrum_seed(
                db,
                t6,
                expected_epics=5,
                expected_sprints=4,
                expected_backlog_stories=13,
                expected_sprint_story_counts={1: 6, 2: 6, 3: 5, 4: 5},
                sprint_story_states=T6_SPRINT_STORY_STATES,
                forbid_legacy_uat_states=True,
                blocked_story_titles=frozenset({"Reserva de stock para pedidos"}),
            )
        )
    if t7 is None:
        report.results.append(
            ProjectValidationResult(
                project_id=uuid.UUID(int=0),
                template_slug=T7_TEMPLATE,
                nombre="(missing)",
                issues=[ValidationIssue("project", f"Proyecto {T7_TEMPLATE} no encontrado")],
            )
        )
    else:
        report.results.append(
            validate_project_scrum_seed(
                db,
                t7,
                expected_epics=4,
                expected_sprints=3,
                expected_backlog_stories=8,
                expected_sprint_story_counts={1: 4, 2: 5, 3: 4},
                sprint_story_states=T7_SPRINT_STORY_STATES,
                forbid_legacy_uat_states=True,
                blocked_story_titles=frozenset({"Validaciones de stock en checkout"}),
            )
        )
    return report

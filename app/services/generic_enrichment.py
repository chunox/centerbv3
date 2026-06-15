"""Enriquecimiento post-creación de proyectos con packs genéricos (tipos, vistas, datos)."""
from __future__ import annotations

import copy
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import _simple_tarea_workflow
from app.domain.packs.manifest import BlockDef, EntityTypeDef, FieldDef, ViewDef
from app.models.entities import (
    Project,
    ProjectFieldDefinition,
    ProjectRecord,
    ProjectRecordType,
    ProjectRole,
    ProjectRoleCapability,
    ProjectWorkflowDefinition,
)
from app.services.blocks import seed_project_blocks, seed_project_views
from app.services.packs import _seed_pack_workbenches_from_views


def _workflow_for_entity(entity_key: str) -> dict[str, Any]:
    wf = copy.deepcopy(_simple_tarea_workflow())
    for transition in wf["transitions"]:
        transition["required_capabilities"] = [
            cap.replace("record.tarea.", f"record.{entity_key}.")
            for cap in transition["required_capabilities"]
        ]
    return wf


def _entity_caps(entity_key: str) -> list[str]:
    return [
        f"record.{entity_key}.read",
        f"record.{entity_key}.create",
        f"record.{entity_key}.edit",
        f"record.{entity_key}.transition.iniciar",
        f"record.{entity_key}.transition.completar",
        f"record.{entity_key}.transition.cancelar",
    ]


def ensure_entity_type(db: Session, project: Project, spec: EntityTypeDef) -> None:
    from app.services.packs import _seed_record_types_from_manifest
    from app.domain.packs.manifest import PackManifest

    _seed_record_types_from_manifest(
        db,
        project,
        PackManifest(slug=project.pack_slug or "custom", nombre="", entity_types=[spec]),
    )


def ensure_field(
    db: Session,
    project: Project,
    *,
    entity_type_key: str,
    field_key: str,
    label: str,
    field_type: str = "text",
    config: dict | None = None,
    orden: int = 0,
) -> None:
    existing = db.scalar(
        select(ProjectFieldDefinition.id).where(
            ProjectFieldDefinition.project_id == project.id,
            ProjectFieldDefinition.entity_type_key == entity_type_key,
            ProjectFieldDefinition.field_key == field_key,
        )
    )
    if existing:
        return
    db.add(
        ProjectFieldDefinition(
            project_id=project.id,
            entity_type_key=entity_type_key,
            field_key=field_key,
            label=label,
            field_type=field_type,
            config=config or {},
            orden=orden,
            is_system=False,
        )
    )
    db.flush()


def ensure_workflow(db: Session, project: Project, entity_type: str, definition: dict) -> None:
    existing = db.scalar(
        select(ProjectWorkflowDefinition.id).where(
            ProjectWorkflowDefinition.project_id == project.id,
            ProjectWorkflowDefinition.entity_type == entity_type,
            ProjectWorkflowDefinition.is_active.is_(True),
        )
    )
    if existing:
        return
    db.add(
        ProjectWorkflowDefinition(
            project_id=project.id,
            entity_type=entity_type,
            version=1,
            is_active=True,
            definition=definition,
        )
    )
    db.flush()


from app.services.role_capabilities import ensure_role_capabilities


def add_block_and_view(
    db: Session,
    project: Project,
    *,
    block: BlockDef,
    view: ViewDef,
) -> None:
    seed_project_blocks(db, project, [block])
    seed_project_views(db, project, [view])
    _seed_pack_workbenches_from_views(db, project)


def sync_project_navigation(db: Session, project: Project) -> None:
    _seed_pack_workbenches_from_views(db, project)


def enrich_evento_project(
    db: Session,
    project: Project,
    *,
    evento_root_id: uuid.UUID,
    pm_id: uuid.UUID,
    today: date,
) -> dict[str, int]:
    """Ponentes, Gantt operativo, actividad y campos extra."""
    ensure_entity_type(
        db,
        project,
        EntityTypeDef(
            key="ponente",
            label="Ponente",
            hierarchy="child",
            parent_type="evento",
            parent_type_keys=["evento"],
            fields=[
                FieldDef(id="empresa", label="Empresa", type="text"),
                FieldDef(id="tema", label="Tema", type="text"),
            ],
            traits={"schedulable": True},
            icon="mic",
            is_system=False,
            orden=3,
        ),
    )
    ensure_field(
        db, project, entity_type_key="tarea", field_key="presupuesto", label="Presupuesto (USD)", field_type="number"
    )
    ensure_field(
        db,
        project,
        entity_type_key="ponente",
        field_key="nivel",
        label="Nivel",
        field_type="select",
        config={"options": ["keynote", "panel", "workshop"]},
    )
    ensure_workflow(db, project, "ponente", _workflow_for_entity("ponente"))

    caps = [
        "workbench.gantt",
        "workbench.activity",
        *_entity_caps("ponente"),
    ]
    ensure_role_capabilities(db, project.id, "coordinador", caps)

    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="gantt",
            key="gantt_ops",
            label="Gantt operativo",
            config={"view_type": "gantt", "entity_type_key": "tarea"},
            orden=25,
        ),
        view=ViewDef(
            key="gantt_ops",
            label="Gantt operativo",
            route="v/gantt-ops",
            icon="gantt-chart",
            section="plan",
            layout={"blocks": [{"project_block_key": "gantt_ops", "width": "full"}]},
            required_capabilities=["workbench.gantt"],
            orden=25,
            view_type="gantt",
            entity_type="tarea",
        ),
    )
    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="checklist",
            key="ponentes",
            label="Ponentes",
            config={"view_type": "checklist", "entity_type_key": "ponente"},
            orden=15,
        ),
        view=ViewDef(
            key="ponentes",
            label="Ponentes",
            route="v/ponentes",
            icon="mic",
            section="plan",
            layout={"blocks": [{"project_block_key": "ponentes", "width": "full"}]},
            required_capabilities=["record.ponente.read"],
            orden=15,
            view_type="checklist",
            entity_type="ponente",
        ),
    )
    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="activity",
            key="actividad",
            label="Actividad",
            config={"view_type": "activity"},
            orden=35,
        ),
        view=ViewDef(
            key="actividad",
            label="Actividad",
            route="v/actividad",
            icon="activity",
            section="track",
            layout={"blocks": [{"project_block_key": "actividad", "width": "full"}]},
            required_capabilities=["workbench.activity"],
            orden=35,
            view_type="custom",
        ),
    )

    from app.services.records.repository import create_record, get_record
    from app.services.workflow.engine import apply_entity_transition

    root = get_record(db, evento_root_id)
    if root and root.estado == "planificacion":
        apply_entity_transition(
            db, project, root, entity_type="evento", action_id="activar", actor_user_id=pm_id
        )

    existing_ponentes = db.scalar(
        select(ProjectRecord.id).where(
            ProjectRecord.project_id == project.id,
            ProjectRecord.record_type == "ponente",
        ).limit(1)
    )
    ponentes_data = [
        ("Dr. Ana Ruiz", "TechCorp", "IA generativa en producto", "keynote"),
        ("Marco Silva", "DataFlow", "Métricas en tiempo real", "panel"),
        ("Laura Kim", "DesignLab", "UX research express", "workshop"),
        ("James Ortiz", "CloudNine", "Escalabilidad serverless", "panel"),
    ]
    created_ponentes = 0
    if existing_ponentes:
        created_ponentes = len(ponentes_data)
    for nombre, empresa, tema, nivel in ([] if existing_ponentes else ponentes_data):
        create_record(
            db,
            project,
            entity_type="ponente",
            titulo=nombre,
            created_by=pm_id,
            parent_id=evento_root_id,
            descripcion=tema,
            data={"empresa": empresa, "tema": tema, "nivel": nivel},
        )
        created_ponentes += 1

    db.commit()
    return {"ponentes": created_ponentes, "views_added": 3}


def enrich_creativo_project(
    db: Session,
    project: Project,
    *,
    campana_root_id: uuid.UUID,
    pm_id: uuid.UUID,
) -> dict[str, int]:
    """Briefs, checklist de entregables y campo canal."""
    ensure_entity_type(
        db,
        project,
        EntityTypeDef(
            key="brief",
            label="Brief",
            hierarchy="child",
            parent_type="campana",
            parent_type_keys=["campana"],
            fields=[
                FieldDef(id="objetivo", label="Objetivo", type="textarea"),
                FieldDef(id="audiencia", label="Audiencia", type="text"),
            ],
            icon="file-text",
            is_system=False,
            orden=3,
        ),
    )
    ensure_field(
        db,
        project,
        entity_type_key="entregable",
        field_key="canal",
        label="Canal",
        field_type="select",
        config={"options": ["tv", "digital", "social", "ooh"]},
    )
    ensure_workflow(db, project, "brief", _workflow_for_entity("brief"))

    caps = ["workbench.checklist", *_entity_caps("brief")]
    ensure_role_capabilities(db, project.id, "pm", caps)

    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="checklist",
            key="briefs",
            label="Briefs",
            config={"view_type": "checklist", "entity_type_key": "brief"},
            orden=15,
        ),
        view=ViewDef(
            key="briefs",
            label="Briefs",
            route="v/briefs",
            icon="file-text",
            section="plan",
            layout={"blocks": [{"project_block_key": "briefs", "width": "full"}]},
            required_capabilities=["record.brief.read"],
            orden=15,
            view_type="checklist",
            entity_type="brief",
        ),
    )
    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="checklist",
            key="entregables_list",
            label="Lista entregables",
            config={"view_type": "checklist", "entity_type_key": "entregable"},
            orden=25,
        ),
        view=ViewDef(
            key="entregables_list",
            label="Lista entregables",
            route="v/lista-entregables",
            icon="list-checks",
            section="plan",
            layout={"blocks": [{"project_block_key": "entregables_list", "width": "full"}]},
            required_capabilities=["record.entregable.read"],
            orden=25,
            view_type="checklist",
            entity_type="entregable",
        ),
    )

    from app.services.records.repository import create_record

    existing_briefs = db.scalar(
        select(ProjectRecord.id).where(
            ProjectRecord.project_id == project.id,
            ProjectRecord.record_type == "brief",
        ).limit(1)
    )
    briefs = [
        ("Brief awareness", "Posicionar marca verano", "18-35 urbano"),
        ("Brief conversión", "Tráfico a landing promo", "Compradores recurrentes"),
        ("Brief branding", "Refrescar identidad visual", "Público general"),
    ]
    if existing_briefs:
        briefs = []
    for titulo, objetivo, audiencia in briefs:
        create_record(
            db,
            project,
            entity_type="brief",
            titulo=titulo,
            created_by=pm_id,
            parent_id=campana_root_id,
            descripcion=objetivo,
            data={"objetivo": objetivo, "audiencia": audiencia},
        )

    db.commit()
    return {"briefs": len(briefs), "views_added": 2}


def enrich_simple_project(
    db: Session,
    project: Project,
    *,
    fase_ids: list[uuid.UUID],
    pm_id: uuid.UUID,
) -> dict[str, int]:
    """Hallazgos, tablero de tareas y campo horas."""
    ensure_entity_type(
        db,
        project,
        EntityTypeDef(
            key="hallazgo",
            label="Hallazgo",
            hierarchy="child",
            parent_type="fase",
            parent_type_keys=["fase"],
            fields=[FieldDef(id="impacto", label="Impacto", type="select", options=["alto", "medio", "bajo"])],
            icon="lightbulb",
            is_system=False,
            orden=3,
        ),
    )
    ensure_field(
        db, project, entity_type_key="tarea", field_key="horas", label="Horas estimadas", field_type="number"
    )
    ensure_workflow(db, project, "hallazgo", _workflow_for_entity("hallazgo"))

    caps = ["workbench.board", *_entity_caps("hallazgo")]
    ensure_role_capabilities(db, project.id, "owner", caps)

    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="board",
            key="tablero_tareas",
            label="Tablero tareas",
            config={
                "view_type": "board",
                "entity_type_key": "tarea",
                "queue_filter": {"entity_types": ["tarea"], "state_categories": ["todo", "active"]},
            },
            orden=15,
        ),
        view=ViewDef(
            key="tablero_tareas",
            label="Tablero tareas",
            route="v/tablero",
            icon="columns-3",
            section="plan",
            layout={"blocks": [{"project_block_key": "tablero_tareas", "width": "full"}]},
            required_capabilities=["workbench.board"],
            orden=15,
            view_type="board",
            entity_type="tarea",
        ),
    )
    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="checklist",
            key="hallazgos",
            label="Hallazgos",
            config={"view_type": "checklist", "entity_type_key": "hallazgo"},
            orden=40,
        ),
        view=ViewDef(
            key="hallazgos",
            label="Hallazgos",
            route="v/hallazgos",
            icon="lightbulb",
            section="track",
            layout={"blocks": [{"project_block_key": "hallazgos", "width": "full"}]},
            required_capabilities=["record.hallazgo.read"],
            orden=40,
            view_type="checklist",
            entity_type="hallazgo",
        ),
    )

    from app.services.records.repository import create_record

    existing_hallazgos = db.scalar(
        select(ProjectRecord.id).where(
            ProjectRecord.project_id == project.id,
            ProjectRecord.record_type == "hallazgo",
        ).limit(1)
    )
    hallazgos_spec = [
        ("Brecha en gobernanza de datos", "alto"),
        ("Procesos manuales repetitivos", "medio"),
        ("Falta de KPIs compartidos", "alto"),
        ("Resistencia al cambio en campo", "medio"),
    ]
    created = 0
    if existing_hallazgos:
        created = len(hallazgos_spec)
    for i, (titulo, impacto) in enumerate([] if existing_hallazgos else hallazgos_spec):
        if i >= len(fase_ids):
            break
        create_record(
            db,
            project,
            entity_type="hallazgo",
            titulo=titulo,
            created_by=pm_id,
            parent_id=fase_ids[i],
            descripcion=f"Hallazgo identificado en {titulo.lower()}.",
            data={"impacto": impacto},
        )
        created += 1

    db.commit()
    return {"hallazgos": created, "views_added": 2}

"""Catálogo de packs sistema y workflows mínimos para packs genéricos."""
from __future__ import annotations

import copy
from typing import Any

from app.domain.packs.manifest import (
    EntityTypeDef,
    FieldDef,
    PackManifest,
    PackRoleDef,
    PackViewDef,
    PackWorkbenchDef,
)

LEGACY_ENTITY_TYPES = ("feature", "task", "query", "report", "milestone")


def _simple_tarea_workflow() -> dict[str, Any]:
    return {
        "initial_state": "pendiente",
        "terminal_states": ["hecho", "cancelado"],
        "states": [
            {"key": "pendiente", "label": "Pendiente", "category": "todo", "badge": "muted"},
            {"key": "en_curso", "label": "En curso", "category": "active", "badge": "info"},
            {"key": "hecho", "label": "Hecho", "category": "done", "badge": "success", "is_terminal": True},
            {"key": "cancelado", "label": "Cancelado", "category": "terminal", "badge": "muted", "is_terminal": True},
        ],
        "transitions": [
            {
                "id": "iniciar",
                "label": "Iniciar",
                "from": ["pendiente"],
                "to": "en_curso",
                "required_capabilities": ["record.tarea.transition.iniciar"],
                "enabled": True,
            },
            {
                "id": "completar",
                "label": "Completar",
                "from": ["en_curso"],
                "to": "hecho",
                "required_capabilities": ["record.tarea.transition.completar"],
                "enabled": True,
            },
            {
                "id": "cancelar",
                "label": "Cancelar",
                "from": ["pendiente", "en_curso"],
                "to": "cancelado",
                "required_capabilities": ["record.tarea.transition.cancelar"],
                "enabled": True,
            },
        ],
    }


def _entregable_workflow() -> dict[str, Any]:
    return {
        "initial_state": "borrador",
        "terminal_states": ["aprobado", "cancelado"],
        "states": [
            {"key": "borrador", "label": "Borrador", "category": "draft", "badge": "muted"},
            {"key": "en_revision", "label": "En revisión", "category": "active", "badge": "info"},
            {
                "key": "pendiente_cliente",
                "label": "Pendiente cliente",
                "category": "inbox",
                "badge": "accent",
            },
            {
                "key": "aprobado",
                "label": "Aprobado",
                "category": "done",
                "badge": "success",
                "is_terminal": True,
            },
            {
                "key": "cancelado",
                "label": "Cancelado",
                "category": "terminal",
                "badge": "muted",
                "is_terminal": True,
            },
        ],
        "transitions": [
            {
                "id": "enviar_revision",
                "label": "Enviar a revisión",
                "from": ["borrador"],
                "to": "en_revision",
                "required_capabilities": ["record.entregable.transition.enviar_revision"],
                "enabled": True,
            },
            {
                "id": "solicitar_aprobacion",
                "label": "Solicitar aprobación",
                "from": ["en_revision"],
                "to": "pendiente_cliente",
                "required_capabilities": ["record.entregable.transition.solicitar_aprobacion"],
                "enabled": True,
            },
            {
                "id": "aprobar",
                "label": "Aprobar",
                "from": ["pendiente_cliente"],
                "to": "aprobado",
                "required_capabilities": ["record.entregable.transition.aprobar"],
                "enabled": True,
            },
            {
                "id": "rechazar",
                "label": "Rechazar",
                "from": ["pendiente_cliente", "en_revision"],
                "to": "borrador",
                "required_capabilities": ["record.entregable.transition.rechazar"],
                "enabled": True,
            },
            {
                "id": "cancelar",
                "label": "Cancelar",
                "from": ["borrador", "en_revision", "pendiente_cliente"],
                "to": "cancelado",
                "required_capabilities": ["record.entregable.transition.cancelar"],
                "enabled": True,
            },
        ],
    }


def _evento_workflow() -> dict[str, Any]:
    return {
        "initial_state": "planificacion",
        "terminal_states": ["finalizado", "cancelado"],
        "states": [
            {"key": "planificacion", "label": "Planificación", "category": "active", "badge": "info"},
            {"key": "en_curso", "label": "En curso", "category": "active", "badge": "accent"},
            {"key": "finalizado", "label": "Finalizado", "category": "done", "badge": "success", "is_terminal": True},
            {"key": "cancelado", "label": "Cancelado", "category": "terminal", "badge": "muted", "is_terminal": True},
        ],
        "transitions": [
            {
                "id": "activar",
                "label": "Activar",
                "from": ["planificacion"],
                "to": "en_curso",
                "required_capabilities": ["record.evento.transition.activar"],
                "enabled": True,
            },
            {
                "id": "finalizar",
                "label": "Finalizar",
                "from": ["en_curso"],
                "to": "finalizado",
                "required_capabilities": ["record.evento.transition.finalizar"],
                "enabled": True,
            },
        ],
    }


def pack_simple_manifest() -> PackManifest:
    caps_owner = [
        "record.fase.read",
        "record.fase.create",
        "record.fase.edit",
        "record.tarea.read",
        "record.tarea.create",
        "record.tarea.edit",
        "record.tarea.transition.iniciar",
        "record.tarea.transition.completar",
        "record.tarea.transition.cancelar",
        "workbench.timeline",
        "workbench.gantt",
        "workbench.checklist",
        "project.settings.edit",
        "project.roles.manage",
    ]
    return PackManifest(
        slug="simple",
        nombre="Proyecto simple",
        descripcion="Fases, tareas y checklist. Ideal para consultoría, personal u ONG.",
        entity_types=[
            EntityTypeDef(key="fase", label="Fase", hierarchy="root", orden=1),
            EntityTypeDef(
                key="tarea",
                label="Tarea",
                hierarchy="child",
                parent_type="fase",
                parent_of=[],
                fields=[
                    FieldDef(id="proveedor", label="Responsable externo", type="text"),
                ],
                orden=2,
            ),
        ],
        views=[
            PackViewDef(key="checklist", type="checklist", label="Checklist", entity_type="tarea", workbench_key="checklist"),
            PackViewDef(key="timeline", type="timeline", label="Timeline", entity_types=["fase", "tarea"], workbench_key="timeline"),
            PackViewDef(key="gantt", type="gantt", label="Gantt", entity_types=["fase", "tarea"], workbench_key="gantt"),
        ],
        workflows={"fase": _simple_tarea_workflow(), "tarea": _simple_tarea_workflow()},
        roles=[PackRoleDef(slug="owner", nombre="Responsable", capabilities=caps_owner, is_system=True)],
        workbenches=[
            PackWorkbenchDef(
                key="checklist",
                label="Checklist",
                route="v/checklist",
                icon="list-checks",
                section="plan",
                view_type="checklist",
                entity_type="tarea",
                required_capabilities=["workbench.checklist"],
                orden=10,
            ),
            PackWorkbenchDef(
                key="timeline",
                label="Timeline",
                route="v/timeline",
                icon="calendar-range",
                section="plan",
                view_type="timeline",
                entity_types=["fase", "tarea"],
                required_capabilities=["workbench.timeline"],
                orden=20,
            ),
            PackWorkbenchDef(
                key="gantt",
                label="Gantt",
                route="v/gantt",
                icon="gantt-chart",
                section="plan",
                view_type="gantt",
                entity_type="tarea",
                required_capabilities=["workbench.gantt"],
                orden=30,
            ),
        ],
    )


def pack_evento_manifest() -> PackManifest:
    caps = [
        "record.evento.read",
        "record.evento.create",
        "record.evento.edit",
        "record.evento.transition.activar",
        "record.evento.transition.finalizar",
        "record.tarea.read",
        "record.tarea.create",
        "record.tarea.edit",
        "record.tarea.transition.iniciar",
        "record.tarea.transition.completar",
        "workbench.checklist",
        "workbench.timeline",
        "project.settings.edit",
        "project.roles.manage",
    ]
    return PackManifest(
        slug="evento",
        nombre="Evento",
        descripcion="Conciertos, conferencias y casamientos con checklist y fechas críticas.",
        entity_types=[
            EntityTypeDef(
                key="evento",
                label="Evento",
                hierarchy="root",
                fields=[FieldDef(id="lugar", label="Lugar", type="text")],
                orden=1,
            ),
            EntityTypeDef(
                key="tarea",
                label="Tarea",
                hierarchy="child",
                parent_type="evento",
                fields=[
                    FieldDef(id="proveedor", label="Proveedor", type="text"),
                    FieldDef(id="fecha_limite", label="Fecha límite", type="date"),
                ],
                orden=2,
            ),
        ],
        views=[
            PackViewDef(key="checklist", type="checklist", entity_type="tarea", workbench_key="checklist"),
            PackViewDef(key="timeline", type="timeline", entity_types=["evento", "tarea"], workbench_key="timeline"),
        ],
        workflows={"evento": _evento_workflow(), "tarea": _simple_tarea_workflow()},
        roles=[PackRoleDef(slug="coordinador", nombre="Coordinador", capabilities=caps, is_system=True)],
        workbenches=[
            PackWorkbenchDef(
                key="checklist",
                label="Checklist",
                route="v/checklist",
                icon="list-checks",
                view_type="checklist",
                entity_type="tarea",
                required_capabilities=["workbench.checklist"],
                orden=10,
            ),
            PackWorkbenchDef(
                key="timeline",
                label="Cronograma",
                route="v/timeline",
                icon="calendar-range",
                view_type="timeline",
                required_capabilities=["workbench.timeline"],
                orden=20,
            ),
        ],
    )


def pack_creativo_manifest() -> PackManifest:
    caps = [
        "record.campana.read",
        "record.campana.create",
        "record.campana.edit",
        "record.entregable.read",
        "record.entregable.create",
        "record.entregable.edit",
        "record.entregable.transition.enviar_revision",
        "record.entregable.transition.solicitar_aprobacion",
        "record.entregable.transition.aprobar",
        "record.entregable.transition.rechazar",
        "record.entregable.transition.cancelar",
        "workbench.board",
        "workbench.inbox",
        "project.settings.edit",
        "project.roles.manage",
    ]
    return PackManifest(
        slug="creativo",
        nombre="Creativo / Agencia",
        descripcion="Campañas, entregables y aprobaciones de cliente.",
        entity_types=[
            EntityTypeDef(key="campana", label="Campaña", hierarchy="root", orden=1),
            EntityTypeDef(
                key="entregable",
                label="Entregable",
                hierarchy="child",
                parent_type="campana",
                fields=[FieldDef(id="version", label="Versión", type="number")],
                orden=2,
            ),
        ],
        views=[
            PackViewDef(key="board", type="board", entity_type="entregable", workbench_key="board"),
            PackViewDef(key="inbox", type="inbox", entity_type="entregable", workbench_key="inbox"),
        ],
        workflows={"campana": _simple_tarea_workflow(), "entregable": _entregable_workflow()},
        roles=[
            PackRoleDef(slug="pm", nombre="Productor", capabilities=caps, is_system=True),
            PackRoleDef(
                slug="cliente",
                nombre="Cliente",
                capabilities=[
                    "record.entregable.read",
                    "record.entregable.transition.aprobar",
                    "record.entregable.transition.rechazar",
                    "workbench.inbox",
                ],
                is_system=True,
                orden=2,
            ),
        ],
        workbenches=[
            PackWorkbenchDef(
                key="board",
                label="Tablero",
                route="v/board",
                icon="columns-3",
                view_type="board",
                entity_type="entregable",
                required_capabilities=["workbench.board"],
                queue_filter={"entity_types": ["entregable"], "state_categories": ["draft", "active"]},
                orden=10,
            ),
            PackWorkbenchDef(
                key="inbox",
                label="Aprobaciones",
                route="v/inbox",
                icon="inbox",
                view_type="inbox",
                entity_type="entregable",
                required_capabilities=["workbench.inbox"],
                queue_filter={"entity_types": ["entregable"], "state_categories": ["inbox"]},
                orden=20,
            ),
        ],
    )


def pack_software_manifest() -> PackManifest:
    return PackManifest(
        slug="software",
        nombre="Software Delivery",
        descripcion="Entrega de software con features, kanban, UAT y cliente.",
        maps_template_slug="t1_cliente_clasico",
        entity_types=[
            EntityTypeDef(key="milestone", label="Hito", storage="legacy", hierarchy="root", orden=1),
            EntityTypeDef(key="feature", label="Feature", storage="legacy", hierarchy="child", parent_type="milestone", orden=2),
            EntityTypeDef(key="task", label="Tarea", storage="legacy", hierarchy="child", parent_type="feature", orden=3),
            EntityTypeDef(key="query", label="Consulta", storage="legacy", hierarchy="child", parent_type="feature", orden=4),
            EntityTypeDef(key="report", label="Reporte", storage="legacy", hierarchy="child", parent_type="feature", orden=5),
        ],
        views=[],
        workflows={},
        roles=[],
        workbenches=[],
    )


SYSTEM_PACKS: dict[str, PackManifest] = {
    "software": pack_software_manifest(),
    "simple": pack_simple_manifest(),
    "evento": pack_evento_manifest(),
    "creativo": pack_creativo_manifest(),
}


def get_pack_manifest(slug: str) -> PackManifest | None:
    return SYSTEM_PACKS.get(slug)

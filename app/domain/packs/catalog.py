"""Catálogo de packs sistema y workflows mínimos para packs genéricos."""
from __future__ import annotations

import copy
from typing import Any

from app.domain.packs.manifest import (
    EntityTypeDef,
    FieldDef,
    FieldDefinitionDef,
    PackManifest,
    PackRoleDef,
    PackViewDef,
    PackWorkbenchDef,
)
from app.domain.capabilities import (
    WORKBENCH_BOARD,
    WORKBENCH_INBOX_CLIENT,
    WORKBENCH_INBOX_GENERIC,
    WORKBENCH_OVERVIEW,
    WORKBENCH_SCOPE,
    WORKBENCH_SETTINGS,
    WORKBENCH_STUDIO,
    WORKBENCH_TEAM,
)

LEGACY_ENTITY_TYPES = ("feature", "task", "query", "report", "milestone")


def _default_workflow_profiles(
    workflows: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {"default": workflows}


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
        "workbench.board",
        "workbench.timeline",
        "workbench.gantt",
        "workbench.checklist",
        "workbench.settings",
        "workbench.studio",
        WORKBENCH_TEAM,
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
                traits={"assignees": True},
                fields=[
                    FieldDef(id="proveedor", label="Responsable externo", type="text"),
                ],
                orden=2,
            ),
        ],
        views=[
            PackViewDef(key="board", type="board", label="Tablero", entity_type="tarea", workbench_key="board"),
            PackViewDef(key="checklist", type="checklist", label="Checklist", entity_type="tarea", workbench_key="checklist"),
            PackViewDef(key="timeline", type="timeline", label="Timeline", entity_types=["fase", "tarea"], workbench_key="timeline"),
            PackViewDef(key="gantt", type="gantt", label="Gantt", entity_types=["fase", "tarea"], workbench_key="gantt"),
        ],
        workflows={"fase": _simple_tarea_workflow(), "tarea": _simple_tarea_workflow()},
        workflow_profiles=_default_workflow_profiles(
            {"fase": _simple_tarea_workflow(), "tarea": _simple_tarea_workflow()}
        ),
        roles=[PackRoleDef(slug="owner", nombre="Responsable", capabilities=caps_owner, is_system=True)],
        workbenches=[
            PackWorkbenchDef(
                key="board",
                label="Tablero",
                route="v/board",
                icon="columns-3",
                section="plan",
                view_type="board",
                entity_type="tarea",
                required_capabilities=["workbench.board"],
                orden=5,
            ),
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
                entity_type="tarea",
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
            PackWorkbenchDef(
                key="team",
                label="Equipo",
                route="team",
                icon="users",
                section="pm",
                view_type="team",
                required_capabilities=[WORKBENCH_TEAM],
                orden=8,
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
        "record.tarea.transition.cancelar",
        "workbench.board",
        "workbench.checklist",
        "workbench.timeline",
        "workbench.settings",
        "workbench.studio",
        WORKBENCH_TEAM,
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
                traits={"assignees": True},
                fields=[
                    FieldDef(id="proveedor", label="Proveedor", type="text"),
                    FieldDef(id="fecha_limite", label="Fecha límite", type="date"),
                ],
                orden=2,
            ),
        ],
        views=[
            PackViewDef(key="board", type="board", label="Tablero", entity_type="tarea", workbench_key="board"),
            PackViewDef(key="checklist", type="checklist", entity_type="tarea", workbench_key="checklist"),
            PackViewDef(key="timeline", type="timeline", entity_types=["evento", "tarea"], workbench_key="timeline"),
        ],
        workflows={"evento": _evento_workflow(), "tarea": _simple_tarea_workflow()},
        workflow_profiles=_default_workflow_profiles(
            {"evento": _evento_workflow(), "tarea": _simple_tarea_workflow()}
        ),
        roles=[PackRoleDef(slug="coordinador", nombre="Coordinador", capabilities=caps, is_system=True)],
        workbenches=[
            PackWorkbenchDef(
                key="board",
                label="Tablero",
                route="v/board",
                icon="columns-3",
                view_type="board",
                entity_type="tarea",
                required_capabilities=["workbench.board"],
                orden=5,
            ),
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
                entity_type="evento",
                required_capabilities=["workbench.timeline"],
                orden=20,
            ),
            PackWorkbenchDef(
                key="team",
                label="Equipo",
                route="team",
                icon="users",
                section="pm",
                view_type="team",
                required_capabilities=[WORKBENCH_TEAM],
                orden=8,
            ),
        ],
    )


def pack_creativo_manifest() -> PackManifest:
    caps_pm = [
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
        WORKBENCH_OVERVIEW,
        WORKBENCH_TEAM,
        WORKBENCH_SCOPE,
        WORKBENCH_BOARD,
        WORKBENCH_INBOX_GENERIC,
        WORKBENCH_SETTINGS,
        WORKBENCH_STUDIO,
        "project.settings.edit",
        "project.roles.manage",
    ]
    caps_diseno = [
        "record.campana.read",
        "record.entregable.read",
        "record.entregable.create",
        "record.entregable.edit",
        "record.entregable.transition.enviar_revision",
        WORKBENCH_SCOPE,
        WORKBENCH_BOARD,
        WORKBENCH_SETTINGS,
    ]
    caps_cliente = [
        "record.entregable.read",
        "record.entregable.transition.aprobar",
        "record.entregable.transition.rechazar",
        WORKBENCH_INBOX_CLIENT,
    ]
    manifest = PackManifest(
        slug="creativo",
        nombre="Creativo / Agencia",
        descripcion="Campañas, entregables y aprobaciones de cliente.",
        entity_types=[
            EntityTypeDef(
                key="campana",
                label="Campaña",
                hierarchy="root",
                icon="megaphone",
                traits={"schedulable": True, "comments": True},
                orden=1,
            ),
            EntityTypeDef(
                key="entregable",
                label="Entregable",
                hierarchy="child",
                parent_type="campana",
                fields=[
                    FieldDef(id="version", label="Versión", type="number"),
                    FieldDef(id="formato", label="Formato", type="text"),
                    FieldDef(id="canal", label="Canal", type="text"),
                ],
                traits={"comments": True, "attachments": True, "kanban": True, "assignees": True},
                orden=2,
            ),
        ],
        field_definitions=[
            FieldDefinitionDef(
                entity_type_key="entregable",
                field_key="version",
                label="Versión",
                field_type="number",
                config={"default": 1, "indexed": True},
                orden=1,
            ),
            FieldDefinitionDef(
                entity_type_key="entregable",
                field_key="formato",
                label="Formato",
                field_type="select",
                config={"options": ["banner", "video", "social", "print", "otro"]},
                orden=2,
            ),
            FieldDefinitionDef(
                entity_type_key="entregable",
                field_key="canal",
                label="Canal",
                field_type="text",
                config={},
                orden=3,
            ),
        ],
        views=[
            PackViewDef(
                key="overview",
                type="custom",
                label="Resumen",
                entity_types=["campana", "entregable"],
                workbench_key="overview",
            ),
            PackViewDef(
                key="scope",
                type="custom",
                label="Campañas",
                entity_types=["campana", "entregable"],
                workbench_key="scope",
            ),
            PackViewDef(
                key="board",
                type="custom",
                label="Tablero",
                entity_type="entregable",
                workbench_key="board",
            ),
            PackViewDef(
                key="inbox_revision",
                type="custom",
                label="Revisión interna",
                entity_type="entregable",
                workbench_key="inbox_revision",
            ),
            PackViewDef(
                key="inbox_cliente",
                type="custom",
                label="Aprobaciones",
                entity_type="entregable",
                workbench_key="inbox_cliente",
            ),
        ],
        workflows={"campana": _simple_tarea_workflow(), "entregable": _entregable_workflow()},
        traits={"supports_external_approval": True},
        workflow_profiles=_default_workflow_profiles(
            {"campana": _simple_tarea_workflow(), "entregable": _entregable_workflow()}
        ),
        roles=[
            PackRoleDef(slug="pm", nombre="Productor", capabilities=caps_pm, is_system=True),
            PackRoleDef(
                slug="diseno",
                nombre="Diseño",
                capabilities=caps_diseno,
                is_system=True,
                orden=2,
            ),
            PackRoleDef(
                slug="cliente",
                nombre="Cliente",
                capabilities=caps_cliente,
                is_system=True,
                orden=3,
            ),
        ],
        workbenches=[
            PackWorkbenchDef(
                key="overview",
                label="Resumen",
                route="v/overview",
                icon="layout-dashboard",
                section="pm",
                view_type="custom",
                custom_view_key="creativo.overview",
                entity_type="entregable",
                required_capabilities=[WORKBENCH_OVERVIEW],
                orden=5,
            ),
            PackWorkbenchDef(
                key="team",
                label="Equipo",
                route="team",
                icon="users",
                section="pm",
                view_type="team",
                required_capabilities=[WORKBENCH_TEAM],
                orden=8,
            ),
            PackWorkbenchDef(
                key="scope",
                label="Campañas",
                route="v/scope",
                icon="folder-tree",
                section="plan",
                view_type="custom",
                custom_view_key="creativo.scope",
                entity_type="campana",
                required_capabilities=[WORKBENCH_SCOPE],
                orden=10,
            ),
            PackWorkbenchDef(
                key="board",
                label="Tablero",
                route="v/board",
                icon="columns-3",
                section="plan",
                view_type="custom",
                custom_view_key="creativo.board",
                entity_type="entregable",
                required_capabilities=[WORKBENCH_BOARD],
                queue_filter={"entity_types": ["entregable"], "state_categories": ["draft", "active"]},
                orden=15,
            ),
            PackWorkbenchDef(
                key="inbox_revision",
                label="Revisión interna",
                route="v/revision",
                icon="eye",
                section="pm",
                view_type="custom",
                custom_view_key="creativo.inbox_revision",
                entity_type="entregable",
                required_capabilities=[WORKBENCH_INBOX_GENERIC],
                queue_filter={"entity_types": ["entregable"], "state_categories": ["active"]},
                orden=20,
            ),
            PackWorkbenchDef(
                key="inbox_cliente",
                label="Aprobaciones",
                route="v/aprobaciones",
                icon="inbox",
                section="client",
                view_type="custom",
                custom_view_key="creativo.inbox_cliente",
                entity_type="entregable",
                required_capabilities=[WORKBENCH_INBOX_CLIENT],
                queue_filter={"entity_types": ["entregable"], "state_categories": ["inbox"]},
                orden=25,
            ),
        ],
    )
    from app.services.communication.creativo_comm_rules import creativo_communication_rules

    return manifest.model_copy(
        update={"communication_rules": [r.model_dump() for r in creativo_communication_rules()]}
    )


def pack_software_manifest() -> PackManifest:
    from app.domain.packs.software_pack import pack_software_manifest as _legacy

    return _legacy()


def pack_software_waterfall_manifest() -> PackManifest:
    from app.domain.packs.software_pack import pack_software_waterfall_manifest as _wf

    return _wf()


def pack_software_scrum_manifest() -> PackManifest:
    from app.domain.packs.software_pack import pack_software_scrum_manifest as _sc

    return _sc()


def pack_marketing360_manifest() -> PackManifest:
    from app.domain.packs.marketing360_pack import pack_marketing360_manifest as _full

    return _full()


SYSTEM_PACKS: dict[str, PackManifest] = {
    "software": pack_software_manifest(),
    "software-waterfall": pack_software_waterfall_manifest(),
    "software-scrum": pack_software_scrum_manifest(),
    "simple": pack_simple_manifest(),
    "evento": pack_evento_manifest(),
    "creativo": pack_creativo_manifest(),
    "marketing360": pack_marketing360_manifest(),
}


def get_pack_manifest(slug: str) -> PackManifest | None:
    return SYSTEM_PACKS.get(slug)

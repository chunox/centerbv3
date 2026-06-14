"""Pack Marketing 360° — campañas, piezas de contenido y flujo de producción 7 estados."""
from __future__ import annotations

from typing import Any

from app.domain.capabilities import (
    WORKBENCH_BOARD,
    WORKBENCH_GANTT,
    WORKBENCH_INBOX_CLIENT,
    WORKBENCH_MY_TASKS,
    WORKBENCH_OVERVIEW,
    WORKBENCH_SCOPE,
    WORKBENCH_SETTINGS,
    WORKBENCH_STUDIO,
    WORKBENCH_TEAM,
    WORKBENCH_TIMELINE,
)
from app.domain.packs.catalog import _default_workflow_profiles
from app.domain.packs.manifest import (
    EntityTypeDef,
    FieldDef,
    FieldDefinitionDef,
    PackManifest,
    PackRoleDef,
    PackViewDef,
    PackWorkbenchDef,
)

M360 = "marketing360"


def _cap(entity: str, action: str) -> str:
    return f"record.{entity}.transition.{action}"


def _pieza_workflow() -> dict[str, Any]:
    states = [
        {"key": "backlog", "label": "Backlog / Ideas", "category": "backlog", "badge": "muted"},
        {"key": "redaccion", "label": "En Redacción", "category": "draft", "badge": "accent"},
        {"key": "diseno_edicion", "label": "En Diseño / Edición", "category": "active", "badge": "info"},
        {"key": "control_calidad", "label": "Control de Calidad", "category": "active", "badge": "warning"},
        {
            "key": "esperando_aprobacion",
            "label": "Esperando Aprobación",
            "category": "inbox",
            "badge": "accent",
        },
        {"key": "programado", "label": "Programado / Listo", "category": "pending", "badge": "success"},
        {"key": "publicado", "label": "Publicado / Activo", "category": "done", "badge": "success", "is_terminal": True},
        {"key": "descartado", "label": "Descartado", "category": "terminal", "badge": "muted", "is_terminal": True},
    ]
    transitions: list[dict[str, Any]] = [
        {
            "id": "iniciar_redaccion",
            "label": "→ En redacción",
            "from": ["backlog"],
            "to": "redaccion",
            "required_capabilities": [_cap("pieza", "iniciar_redaccion")],
            "allowed_role_slugs": ["pm", "copy"],
            "enabled": True,
        },
        {
            "id": "enviar_diseno",
            "label": "→ Diseño / edición",
            "from": ["redaccion"],
            "to": "diseno_edicion",
            "required_capabilities": [_cap("pieza", "enviar_diseno")],
            "allowed_role_slugs": ["copy", "pm"],
            "enabled": True,
            "side_effects": [
                {"type": "notify_role", "target": {"role_slug": "diseno"}},
                {"type": "set_field", "field_key": "prioridad", "value": "alta"},
            ],
        },
        {
            "id": "enviar_qc",
            "label": "→ Control de calidad",
            "from": ["diseno_edicion"],
            "to": "control_calidad",
            "required_capabilities": [_cap("pieza", "enviar_qc")],
            "allowed_role_slugs": ["diseno", "copy", "pm"],
            "enabled": True,
        },
        {
            "id": "saltar_a_aprobacion",
            "label": "Saltar QC → Aprobación",
            "from": ["diseno_edicion"],
            "to": "esperando_aprobacion",
            "required_capabilities": [_cap("pieza", "solicitar_aprobacion")],
            "allowed_role_slugs": ["pm"],
            "enabled": True,
            "side_effects": [
                {"type": "notify_role", "target": {"role_slug": "cliente"}},
                {"type": "set_field", "field_key": "review_locked", "value": True},
            ],
        },
        {
            "id": "devolver_diseno",
            "label": "← Volver a diseño",
            "from": ["control_calidad"],
            "to": "diseno_edicion",
            "required_capabilities": [_cap("pieza", "devolver_diseno")],
            "allowed_role_slugs": ["pm"],
            "enabled": True,
        },
        {
            "id": "solicitar_aprobacion",
            "label": "→ Esperando aprobación",
            "from": ["control_calidad"],
            "to": "esperando_aprobacion",
            "required_capabilities": [_cap("pieza", "solicitar_aprobacion")],
            "allowed_role_slugs": ["pm"],
            "enabled": True,
            "side_effects": [
                {"type": "notify_role", "target": {"role_slug": "cliente"}},
                {"type": "set_field", "field_key": "review_locked", "value": True},
            ],
        },
        {
            "id": "aprobar",
            "label": "Aprobar",
            "from": ["esperando_aprobacion"],
            "to": "programado",
            "required_capabilities": [_cap("pieza", "aprobar")],
            "allowed_role_slugs": ["cliente", "pm"],
            "enabled": True,
            "side_effects": [
                {"type": "set_field", "field_key": "review_locked", "value": False},
            ],
        },
        {
            "id": "rechazar",
            "label": "Solicitar cambios",
            "from": ["esperando_aprobacion"],
            "to": "diseno_edicion",
            "required_capabilities": [_cap("pieza", "rechazar")],
            "allowed_role_slugs": ["cliente", "pm"],
            "enabled": True,
            "form_fields": [
                {
                    "id": "motivo",
                    "label": "¿Qué hay que cambiar?",
                    "type": "textarea",
                    "required": True,
                },
            ],
            "side_effects": [
                {"type": "set_field", "field_key": "review_locked", "value": False},
            ],
        },
        {
            "id": "publicar",
            "label": "→ Publicado",
            "from": ["programado"],
            "to": "publicado",
            "required_capabilities": [_cap("pieza", "publicar")],
            "allowed_role_slugs": ["pm", "social"],
            "enabled": True,
            "side_effects": [
                {"type": "finalize_parent_when_siblings_done", "target_state": "finalizada"},
            ],
        },
        {
            "id": "descartar",
            "label": "Descartar",
            "from": ["backlog", "redaccion", "diseno_edicion", "control_calidad", "esperando_aprobacion", "programado"],
            "to": "descartado",
            "required_capabilities": [_cap("pieza", "descartar")],
            "allowed_role_slugs": ["pm"],
            "enabled": True,
        },
    ]
    return {
        "initial_state": "backlog",
        "terminal_states": ["publicado", "descartado"],
        "states": states,
        "transitions": transitions,
    }


def _campana_workflow() -> dict[str, Any]:
    return {
        "initial_state": "planificacion",
        "terminal_states": ["finalizada", "cancelada"],
        "states": [
            {"key": "planificacion", "label": "Planificación", "category": "draft", "badge": "muted"},
            {"key": "en_produccion", "label": "En producción", "category": "active", "badge": "info"},
            {"key": "en_pauta", "label": "En pauta", "category": "active", "badge": "accent"},
            {"key": "finalizada", "label": "Finalizada", "category": "done", "badge": "success", "is_terminal": True},
            {"key": "cancelada", "label": "Cancelada", "category": "terminal", "badge": "muted", "is_terminal": True},
        ],
        "transitions": [
            {
                "id": "iniciar_produccion",
                "label": "Iniciar producción",
                "from": ["planificacion"],
                "to": "en_produccion",
                "required_capabilities": [_cap("campana", "iniciar_produccion")],
                "enabled": True,
            },
            {
                "id": "activar_pauta",
                "label": "Activar pauta",
                "from": ["en_produccion"],
                "to": "en_pauta",
                "required_capabilities": [_cap("campana", "activar_pauta")],
                "enabled": True,
            },
            {
                "id": "finalizar",
                "label": "Finalizar campaña",
                "from": ["en_produccion", "en_pauta"],
                "to": "finalizada",
                "required_capabilities": [_cap("campana", "finalizar")],
                "enabled": True,
            },
            {
                "id": "cancelar",
                "label": "Cancelar",
                "from": ["planificacion", "en_produccion", "en_pauta"],
                "to": "cancelada",
                "required_capabilities": [_cap("campana", "cancelar")],
                "enabled": True,
            },
        ],
    }


def _pieza_transition_caps(*ids: str) -> list[str]:
    return [_cap("pieza", i) for i in ids]


def pack_marketing360_manifest() -> PackManifest:
    pieza_all_trans = [
        "iniciar_redaccion",
        "enviar_diseno",
        "enviar_qc",
        "devolver_diseno",
        "solicitar_aprobacion",
        "aprobar",
        "rechazar",
        "publicar",
        "descartar",
    ]
    campana_trans = ["iniciar_produccion", "activar_pauta", "finalizar", "cancelar"]

    caps_pm = [
        "record.campana.read",
        "record.campana.create",
        "record.campana.edit",
        *[_cap("campana", t) for t in campana_trans],
        "record.pieza.read",
        "record.pieza.create",
        "record.pieza.edit",
        *_pieza_transition_caps(*pieza_all_trans),
        WORKBENCH_OVERVIEW,
        WORKBENCH_TEAM,
        WORKBENCH_SCOPE,
        WORKBENCH_BOARD,
        WORKBENCH_MY_TASKS,
        WORKBENCH_TIMELINE,
        WORKBENCH_GANTT,
        WORKBENCH_INBOX_CLIENT,
        WORKBENCH_SETTINGS,
        WORKBENCH_STUDIO,
        "project.settings.edit",
        "project.roles.manage",
    ]
    caps_copy = [
        "record.campana.read",
        "record.pieza.read",
        "record.pieza.create",
        "record.pieza.edit",
        *_pieza_transition_caps("iniciar_redaccion", "enviar_diseno", "enviar_qc"),
        WORKBENCH_SCOPE,
        WORKBENCH_BOARD,
        WORKBENCH_MY_TASKS,
        WORKBENCH_SETTINGS,
    ]
    caps_diseno = [
        "record.campana.read",
        "record.pieza.read",
        "record.pieza.edit",
        *_pieza_transition_caps("enviar_diseno", "enviar_qc"),
        WORKBENCH_BOARD,
        WORKBENCH_MY_TASKS,
        WORKBENCH_SETTINGS,
    ]
    caps_social = [
        "record.campana.read",
        "record.pieza.read",
        "record.pieza.edit",
        *_pieza_transition_caps("publicar"),
        WORKBENCH_TIMELINE,
        WORKBENCH_SCOPE,
        WORKBENCH_SETTINGS,
    ]
    caps_cliente = [
        "record.pieza.read",
        *_pieza_transition_caps("aprobar", "rechazar"),
        WORKBENCH_INBOX_CLIENT,
    ]

    workflows = {"campana": _campana_workflow(), "pieza": _pieza_workflow()}

    from app.services.communication.marketing360_comm_rules import (
        marketing360_communication_rules,
    )

    m360_rules = [r.model_dump() for r in marketing360_communication_rules()]

    return PackManifest(
        slug=M360,
        nombre="Marketing 360°",
        descripcion="Gestión de campañas de marketing: briefing, producción 7 estados, calendario y aprobaciones.",
        traits={"supports_external_approval": True, "marketing_template": True},
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
                key="pieza",
                label="Contenido",
                hierarchy="child",
                parent_type="campana",
                fields=[
                    FieldDef(id="canal", label="Canal", type="select"),
                    FieldDef(id="formato", label="Formato", type="select"),
                    FieldDef(id="prioridad", label="Prioridad", type="select"),
                    FieldDef(id="fecha_publicacion", label="Fecha publicación", type="date"),
                ],
                traits={
                    "comments": True,
                    "attachments": True,
                    "kanban": True,
                    "assignees": True,
                },
                orden=2,
            ),
        ],
        field_definitions=[
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="objetivo",
                label="Objetivo principal",
                field_type="select",
                config={
                    "options": [
                        "conversion",
                        "leads",
                        "trafico",
                        "awareness",
                        "lanzamiento",
                    ],
                    "labels": {
                        "conversion": "Conversión",
                        "leads": "Captación de leads",
                        "trafico": "Tráfico",
                        "awareness": "Brand awareness",
                        "lanzamiento": "Lanzamiento",
                    },
                },
                orden=1,
            ),
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="buyer_persona",
                label="Público objetivo / Buyer persona",
                field_type="textarea",
                config={},
                orden=2,
            ),
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="canales",
                label="Canales de difusión",
                field_type="multi_select",
                config={
                    "options": [
                        "meta_ads",
                        "google_ads",
                        "newsletter",
                        "organic_social",
                        "linkedin",
                        "blog_seo",
                    ],
                },
                orden=3,
            ),
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="presupuesto_produccion",
                label="Presupuesto producción",
                field_type="number",
                config={"currency": True},
                orden=4,
            ),
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="presupuesto_pauta",
                label="Presupuesto pauta",
                field_type="number",
                config={"currency": True},
                orden=5,
            ),
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="kpi_exito",
                label="KPI de éxito",
                field_type="text",
                config={},
                orden=6,
            ),
            FieldDefinitionDef(
                entity_type_key="campana",
                field_key="fecha_lanzamiento",
                label="Fecha de lanzamiento",
                field_type="date",
                config={},
                orden=7,
            ),
            FieldDefinitionDef(
                entity_type_key="pieza",
                field_key="canal",
                label="Canal",
                field_type="select",
                config={
                    "options": [
                        "meta_ads",
                        "google_ads",
                        "newsletter",
                        "organic_social",
                        "linkedin",
                        "blog_seo",
                    ],
                },
                orden=1,
            ),
            FieldDefinitionDef(
                entity_type_key="pieza",
                field_key="formato",
                label="Formato",
                field_type="select",
                config={"options": ["banner", "video", "copy", "carrusel", "reel", "landing"]},
                orden=2,
            ),
            FieldDefinitionDef(
                entity_type_key="pieza",
                field_key="prioridad",
                label="Prioridad",
                field_type="select",
                config={"options": ["baja", "media", "alta", "critica"], "default": "media"},
                orden=3,
            ),
            FieldDefinitionDef(
                entity_type_key="pieza",
                field_key="fecha_publicacion",
                label="Fecha de publicación",
                field_type="date",
                config={},
                orden=4,
            ),
            FieldDefinitionDef(
                entity_type_key="pieza",
                field_key="review_locked",
                label="Revisión bloqueada",
                field_type="checkbox",
                config={"hidden": True},
                orden=5,
            ),
        ],
        views=[
            PackViewDef(key="overview", type="custom", label="Resumen", entity_types=["campana", "pieza"], workbench_key="overview"),
            PackViewDef(key="scope", type="custom", label="Brief / Campañas", entity_types=["campana", "pieza"], workbench_key="scope"),
            PackViewDef(key="board", type="custom", label="Tablero producción", entity_type="pieza", workbench_key="board"),
            PackViewDef(key="mi_produccion", type="custom", label="Mi producción", entity_type="pieza", workbench_key="mi_produccion"),
            PackViewDef(key="calendario", type="custom", label="Calendario", entity_type="pieza", workbench_key="calendario"),
            PackViewDef(key="gantt", type="custom", label="Cronograma", entity_type="pieza", workbench_key="gantt"),
            PackViewDef(key="aprobaciones", type="custom", label="Aprobaciones", entity_type="pieza", workbench_key="aprobaciones"),
        ],
        workflows=workflows,
        workflow_profiles=_default_workflow_profiles(workflows),
        roles=[
            PackRoleDef(slug="pm", nombre="PM / Trafficker", capabilities=caps_pm, is_system=True),
            PackRoleDef(slug="copy", nombre="Copywriter", capabilities=caps_copy, is_system=True, orden=2),
            PackRoleDef(slug="diseno", nombre="Diseño / Edición", capabilities=caps_diseno, is_system=True, orden=3),
            PackRoleDef(slug="social", nombre="Community / SEO", capabilities=caps_social, is_system=True, orden=4),
            PackRoleDef(slug="cliente", nombre="Cliente / CMO", capabilities=caps_cliente, is_system=True, orden=5),
        ],
        workbenches=[
            PackWorkbenchDef(
                key="overview",
                label="Resumen",
                route="v/overview",
                icon="layout-dashboard",
                section="pm",
                view_type="custom",
                custom_view_key=f"{M360}.overview",
                entity_type="pieza",
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
                label="Brief / Campañas",
                route="v/scope",
                icon="folder-tree",
                section="plan",
                view_type="custom",
                custom_view_key=f"{M360}.scope",
                entity_type="campana",
                required_capabilities=[WORKBENCH_SCOPE],
                orden=10,
            ),
            PackWorkbenchDef(
                key="board",
                label="Tablero producción",
                route="v/board",
                icon="columns-3",
                section="plan",
                view_type="custom",
                custom_view_key=f"{M360}.board",
                entity_type="pieza",
                required_capabilities=[WORKBENCH_BOARD],
                queue_filter={"entity_types": ["pieza"], "state_categories": ["backlog", "draft", "active", "pending"]},
                orden=15,
            ),
            PackWorkbenchDef(
                key="mi_produccion",
                label="Mi producción",
                route="v/mi-produccion",
                icon="user-check",
                section="dev",
                view_type="custom",
                custom_view_key=f"{M360}.mi_produccion",
                entity_type="pieza",
                required_capabilities=[WORKBENCH_MY_TASKS],
                queue_filter={"entity_types": ["pieza"], "state_categories": ["draft", "active"]},
                orden=20,
            ),
            PackWorkbenchDef(
                key="calendario",
                label="Calendario de contenidos",
                route="v/calendario",
                icon="calendar",
                section="dev",
                view_type="custom",
                custom_view_key=f"{M360}.calendario",
                entity_type="pieza",
                required_capabilities=[WORKBENCH_TIMELINE],
                queue_filter={"entity_types": ["pieza"], "state_categories": ["pending", "done"]},
                orden=25,
            ),
            PackWorkbenchDef(
                key="gantt",
                label="Cronograma de lanzamiento",
                route="v/gantt",
                icon="gantt-chart",
                section="pm",
                view_type="custom",
                custom_view_key=f"{M360}.gantt",
                entity_type="pieza",
                required_capabilities=[WORKBENCH_GANTT],
                orden=30,
            ),
            PackWorkbenchDef(
                key="aprobaciones",
                label="Portal de aprobaciones",
                route="v/aprobaciones",
                icon="shield-check",
                section="client",
                view_type="custom",
                custom_view_key=f"{M360}.aprobaciones",
                entity_type="pieza",
                required_capabilities=[WORKBENCH_INBOX_CLIENT],
                queue_filter={"entity_types": ["pieza"], "state_categories": ["inbox"]},
                orden=35,
            ),
        ],
        communication_rules=m360_rules,
    )

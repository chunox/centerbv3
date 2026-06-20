"""Manifest completo del pack software delivery."""
from __future__ import annotations

from typing import Any

from app.domain.capabilities import (
    TEMPLATE_ROLE_CAPABILITIES,
    TEMPLATE_ROLE_LABELS,
    WORKBENCH_KANBAN,
    WORKBENCH_INBOX_QA,
    WORKBENCH_SPRINT_BOARD,
    WORKBENCH_SCRUM_CAPACITY,
    WORKBENCH_SCRUM_IMPEDIMENTS,
    WORKBENCH_SCRUM_METRICS,
    WORKBENCH_SCRUM_REFINEMENT,
    WORKBENCH_PRODUCT_BACKLOG,
    WORKBENCH_SPRINT_PLANNING,
)
from app.domain.packs.manifest import (
    BlockDef,
    EntityTypeDef,
    FieldDefinitionDef,
    PackManifest,
    PackRoleDef,
    ViewDef,
)
from app.domain.project_templates import PROJECT_TEMPLATES
from app.domain.workbenches import DEFAULT_WORKBENCHES


def _software_entity_types() -> list[EntityTypeDef]:
    return [
        EntityTypeDef(
            key="milestone",
            label="Hito",
            hierarchy="root",
            icon="flag",
            traits={"schedulable": True, "comments": True, "scope_chain": True},
            orden=1,
        ),
        EntityTypeDef(
            key="feature",
            label="Feature",
            hierarchy="child",
            parent_type="milestone",
            parent_type_keys=["milestone"],
            icon="layers",
            traits={"schedulable": True, "comments": True, "blocking": True, "scope_chain": True},
            orden=2,
        ),
        EntityTypeDef(
            key="task",
            label="Tarea",
            hierarchy="child",
            parent_type="feature",
            parent_type_keys=["feature"],
            icon="check-square",
            traits={
                "assignees": True,
                "attachments": True,
                "dependencies": True,
                "subtasks": True,
                "kanban": True,
                "comments": True,
                "scope_chain": True,
            },
            orden=3,
        ),
        EntityTypeDef(
            key="query",
            label="Consulta",
            hierarchy="child",
            parent_type="feature",
            parent_type_keys=["feature"],
            icon="help-circle",
            traits={"blocking": True, "comments": True},
            orden=4,
        ),
        EntityTypeDef(
            key="report",
            label="Reporte",
            hierarchy="child",
            parent_type="feature",
            parent_type_keys=["feature"],
            icon="bug",
            traits={"spawns": "feature", "comments": True},
            orden=5,
        ),
        EntityTypeDef(
            key="impediment",
            label="Impedimento",
            hierarchy="child",
            parent_type="sprint",
            parent_type_keys=["sprint"],
            icon="alert-triangle",
            traits={"comments": True},
            orden=6,
        ),
        EntityTypeDef(
            key="product_backlog",
            label="Product Backlog",
            hierarchy="root",
            icon="list-ordered",
            traits={"comments": True, "scope_chain": True},
            orden=7,
        ),
        EntityTypeDef(
            key="sprint",
            label="Sprint",
            hierarchy="root",
            icon="timer",
            traits={"schedulable": True, "comments": True, "scope_chain": True},
            orden=8,
        ),
    ]


def _software_field_definitions() -> list[FieldDefinitionDef]:
    return [
        FieldDefinitionDef(
            entity_type_key="milestone",
            field_key="tipo",
            label="Tipo",
            field_type="select",
            config={"options": ["entrega"], "default": "entrega"},
            orden=1,
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="tipo",
            label="Tipo",
            field_type="select",
            config={"options": ["desarrollo", "bug", "mejora"], "required": True, "indexed": True},
            orden=1,
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="prioridad",
            label="Prioridad",
            field_type="select",
            config={"options": ["baja", "media", "alta", "critica"], "default": "media", "indexed": True},
            orden=2,
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="duracion_estimada",
            label="Duración estimada (días)",
            field_type="number",
            config={},
            orden=3,
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="bloqueada",
            label="Bloqueada",
            field_type="checkbox",
            config={"default": False, "indexed": True},
            orden=4,
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="origen_report_id",
            label="Origen reporte",
            field_type="relation",
            config={"relation_entity_type": "report"},
            orden=5,
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="origen_feature_id",
            label="Origen feature",
            field_type="relation",
            config={"relation_entity_type": "feature"},
            orden=6,
        ),
        FieldDefinitionDef(
            entity_type_key="report",
            field_key="tipo",
            label="Tipo",
            field_type="select",
            config={"options": ["bug", "mejora"], "required": True},
            orden=1,
        ),
        FieldDefinitionDef(
            entity_type_key="report",
            field_key="reported_by",
            label="Reportado por",
            field_type="user",
            config={},
            orden=2,
        ),
        FieldDefinitionDef(
            entity_type_key="report",
            field_key="generated_feature_id",
            label="Feature generada",
            field_type="relation",
            config={"relation_entity_type": "feature"},
            orden=3,
        ),
        FieldDefinitionDef(
            entity_type_key="task",
            field_key="estimacion_horas",
            label="Estimación (h)",
            field_type="number",
            config={"allow_decimal": True, "step": 0.5, "min": 0},
            orden=1,
        ),
        # ── Scrum (solo t6/t7) ──────────────────────────────────────────────
        FieldDefinitionDef(
            entity_type_key="sprint",
            field_key="sprint_goal",
            label="Objetivo del Sprint",
            field_type="textarea",
            config={},
            orden=1,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="sprint",
            field_key="horas_planeadas",
            label="Horas planeadas",
            field_type="number",
            config={"min": 0},
            orden=2,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="sprint",
            field_key="capacity_plan",
            label="Plan de capacidad",
            field_type="textarea",
            config={"format": "json_array"},
            orden=3,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="feature",
            field_key="sprint_id",
            label="Sprint",
            field_type="relation",
            config={"relation_entity_type": "sprint"},
            orden=20,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="task",
            field_key="refinement_ready",
            label="Refinement ready",
            field_type="checkbox",
            config={"default": False, "indexed": True},
            orden=21,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="task",
            field_key="criterios_aceptacion",
            label="Criterios de aceptación",
            field_type="textarea",
            config={"format": "json_array"},
            orden=22,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="titulo",
            label="Título",
            field_type="text",
            config={"required": True},
            orden=1,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="sprint_id",
            label="Sprint",
            field_type="relation",
            config={"relation_entity_type": "sprint"},
            orden=2,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="owner_user_id",
            label="Owner",
            field_type="user",
            config={},
            orden=3,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="status",
            label="Estado",
            field_type="select",
            config={"options": ["open", "resolved"], "default": "open", "indexed": True},
            orden=4,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="impacto",
            label="Impacto",
            field_type="textarea",
            config={},
            orden=5,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="resolucion",
            label="Resolución",
            field_type="textarea",
            config={},
            orden=6,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
        FieldDefinitionDef(
            entity_type_key="impediment",
            field_key="raised_at",
            label="Reportado en",
            field_type="datetime",
            config={},
            orden=7,
            template_slugs=["t6_scrum_interno", "t7_scrum_cliente"],
        ),
    ]


def _software_custom_view_key(wb_key: str) -> str | None:
    mapping = {
        "overview": "software.overview",
        "inbox_pm": "software.inbox_pm",
        "inbox_dev": "software.inbox_dev",
        "inbox_qa": "software.inbox_qa",
        "inbox_client": "software.inbox_client",
        "kanban": "software.kanban",
        "my_tasks": "software.kanban",
        "uat": "software.uat",
        "scope": "software.scope",
        "sprint_board": "software.sprint_board",
        "product_backlog": "software.product_backlog",
        "sprint_planning": "software.sprint_planning",
        "scrum_impediments": "software.scrum_impediments",
        "scrum_refinement": "software.scrum_refinement",
        "scrum_capacity": "software.scrum_capacity",
        "scrum_metrics": "software.scrum_metrics",
        "scrum_daily": "software.scrum_daily",
        "scrum_planning_poker": "software.scrum_planning_poker",
        "scrum_sprint_review": "software.scrum_sprint_review",
        "scrum_retro": "software.scrum_retro",
        "scrum_scope": "software.scrum_scope",
        "scrum_kanban": "software.scrum_kanban",
    }
    return mapping.get(wb_key)


def _software_entity_type(wb_key: str) -> str | None:
    mapping = {
        "kanban": "task",
        "my_tasks": "task",
        "uat": "feature",
    }
    return mapping.get(wb_key)


from app.domain.project_templates import SCRUM_TEMPLATE_SLUGS

_SCRUM_SLUGS = sorted(SCRUM_TEMPLATE_SLUGS)
_INTERNO_SLUGS = ["t3_interno_clasico", "t4_interno_pm_tecnico", "t6_scrum_interno"]


def _software_blocks() -> list[BlockDef]:
    blocks: list[BlockDef] = []
    block_slug_map = {
        "overview": "custom",
        "inbox_pm": "custom",
        "inbox_dev": "custom",
        "kanban": "custom",
        "my_tasks": "custom",
        "inbox_qa": "custom",
        "uat": "custom",
        "inbox_client": "custom",
        "scope": "scope",
        "hub": "hub",
        "timeline": "timeline",
        "activity": "activity",
        "team": "team",
        "studio": "studio",
        "settings": "settings",
    }
    for wb in DEFAULT_WORKBENCHES:
        slug = block_slug_map.get(wb["key"], "overview")
        custom_key = _software_custom_view_key(wb["key"])
        entity_type = wb.get("entity_type") or _software_entity_type(wb["key"])
        config: dict[str, Any] = {
            "entity_type_key": entity_type,
            "queue_filter": wb.get("queue_filter"),
            "view_type": "custom" if custom_key else wb.get("view_type", slug),
        }
        if custom_key:
            config["custom_view_key"] = custom_key
        if wb["key"] in {"kanban", "my_tasks"}:
            config["board_config"] = {
                "variant": "editorial",
                "filters": {
                    "search": True,
                    "parent_chain": True,
                    "group_by_parent": True,
                },
                "column_picker": True,
                "card": {"show_assignees": True, "show_parent": True},
            }
        if wb["key"] == "scope":
            config["scope_config"] = {
                "variant": "editorial",
                "levels": ["milestone", "feature", "task"],
                "depth_actions": "any_level",
                "show_summary": True,
                "allow_reparent": True,
            }
        if wb["key"] == "timeline":
            config["entity_types"] = ["milestone", "feature"]
        exclude: list[str] = []
        if wb["key"] == "inbox_client":
            exclude = _INTERNO_SLUGS
        elif wb["key"] == "kanban":
            # En Scrum se seedea el kanban con label "Tareas" (ver abajo)
            exclude = _SCRUM_SLUGS
        elif wb["key"] == "inbox_qa":
            exclude = _SCRUM_SLUGS
        elif wb["key"] == "scope":
            exclude = _SCRUM_SLUGS
        blocks.append(
            BlockDef(
                block_slug=slug,
                key=wb["key"],
                label=wb["label"],
                config=config,
                orden=wb.get("orden", 0),
                exclude_template_slugs=exclude,
            )
        )

    # Scope Scrum v2: product_backlog / sprint → task
    blocks.append(
        BlockDef(
            block_slug="scope",
            key="scope",
            label="Alcance",
            config={
                "entity_type_key": None,
                "view_type": "custom",
                "custom_view_key": "software.scrum_scope",
                "scope_config": {
                    "variant": "editorial",
                    "levels": ["product_backlog", "sprint", "task"],
                    "depth_actions": "any_level",
                    "show_summary": True,
                    "allow_reparent": True,
                },
            },
            orden=40,
            template_slugs=_SCRUM_SLUGS,
        )
    )

    # Kanban con label "Tareas" para proyectos Scrum
    kanban_config: dict[str, Any] = {
        "entity_type_key": "task",
        "view_type": "custom",
        "custom_view_key": "software.scrum_kanban",
        "board_config": {
            "variant": "editorial",
            "filters": {"search": True, "parent_chain": True, "group_by_parent": True},
            "column_picker": True,
            "card": {"show_assignees": True, "show_parent": True},
        },
    }
    blocks.append(
        BlockDef(
            block_slug="custom",
            key="kanban",
            label="Tareas",
            config=kanban_config,
            orden=50,
            template_slugs=_SCRUM_SLUGS,
        )
    )

    # Bandeja QA Scrum (UAT + consultas)
    blocks.append(
        BlockDef(
            block_slug="custom",
            key="inbox_qa",
            label="Bandeja",
            config={
                "view_type": "custom",
                "custom_view_key": "software.inbox_qa_scrum",
            },
            orden=70,
            template_slugs=_SCRUM_SLUGS,
        )
    )

    # Workbenches Scrum exclusivos
    for i, (wb_key, label, icon) in enumerate([
        ("product_backlog", "Product Backlog", "list-ordered"),
        ("sprint_planning", "Sprint Planning", "calendar-clock"),
        ("sprint_board", "Sprint Board", "layout-kanban"),
    ]):
        blocks.append(
            BlockDef(
                block_slug="custom",
                key=wb_key,
                label=label,
                config={"custom_view_key": f"software.{wb_key}", "view_type": "custom"},
                orden=100 + i * 10,
                template_slugs=_SCRUM_SLUGS,
            )
        )
    for i, (wb_key, label, icon) in enumerate([
        ("scrum_refinement", "Refinement", "list-checks"),
        ("scrum_capacity", "Capacity", "gauge"),
        ("scrum_impediments", "Impedimentos", "alert-triangle"),
        ("scrum_daily", "Daily", "timer-reset"),
        ("scrum_planning_poker", "Planning Poker", "dice-5"),
        ("scrum_sprint_review", "Sprint Review", "messages-square"),
        ("scrum_retro", "Retro", "repeat"),
        ("scrum_metrics", "Métricas", "line-chart"),
    ]):
        blocks.append(
            BlockDef(
                block_slug="custom",
                key=wb_key,
                label=label,
                config={"custom_view_key": f"software.{wb_key}", "view_type": "custom"},
                orden=140 + i * 10,
                template_slugs=_SCRUM_SLUGS,
            )
        )
    return blocks


def _software_views() -> list[ViewDef]:
    views: list[ViewDef] = []
    for wb in DEFAULT_WORKBENCHES:
        custom_key = _software_custom_view_key(wb["key"])
        exclude: list[str] = []
        label = wb["label"]
        if wb["key"] == "inbox_client":
            exclude = _INTERNO_SLUGS
        elif wb["key"] == "kanban":
            exclude = _SCRUM_SLUGS
        elif wb["key"] == "inbox_qa":
            exclude = _SCRUM_SLUGS
        views.append(
            ViewDef(
                key=wb["key"],
                label=label,
                route=wb["route"],
                icon=wb.get("icon", "circle"),
                section=wb.get("section", "plan"),
                layout={"blocks": [{"project_block_key": wb["key"], "width": "full"}]},
                required_capabilities=wb.get("required_capabilities", []),
                orden=wb.get("orden", 0),
                view_type="custom" if custom_key else wb.get("view_type", "custom"),  # type: ignore[arg-type]
                entity_type=wb.get("entity_type") or _software_entity_type(wb["key"]),
                queue_filter=wb.get("queue_filter"),
                exclude_template_slugs=exclude,
            )
        )

    # Vista de Kanban con label "Tareas" para Scrum
    views.append(
        ViewDef(
            key="kanban",
            label="Tareas",
            route="kanban",
            icon="columns-3",
            section="dev",
            layout={"blocks": [{"project_block_key": "kanban", "width": "full"}]},
            required_capabilities=[WORKBENCH_KANBAN],
            orden=50,
            template_slugs=_SCRUM_SLUGS,
            view_type="custom",
        )
    )

    views.append(
        ViewDef(
            key="inbox_qa",
            label="Bandeja",
            route="qa/inbox",
            icon="flask-conical",
            section="qa",
            layout={"blocks": [{"project_block_key": "inbox_qa", "width": "full"}]},
            required_capabilities=[WORKBENCH_INBOX_QA],
            orden=70,
            template_slugs=_SCRUM_SLUGS,
            view_type="custom",
        )
    )

    # Vistas Scrum exclusivas (agrupadas en sidebar como tabs bajo «Scrum»)
    scrum_views = [
        ("product_backlog", "Product Backlog", "list-ordered", WORKBENCH_PRODUCT_BACKLOG, 0, True),
        ("sprint_planning", "Sprint Planning", "calendar-clock", WORKBENCH_SPRINT_PLANNING, 1, False),
        ("sprint_board", "Sprint Board", "layout-kanban", WORKBENCH_SPRINT_BOARD, 2, False),
    ]
    for i, (wb_key, label, icon, cap, group_order, is_primary) in enumerate(scrum_views):
        nav: dict[str, Any] = {
            "group": "scrum",
            "group_order": group_order,
            "primary": is_primary,
        }
        if is_primary:
            nav["group_label"] = "Scrum"
        views.append(
            ViewDef(
                key=wb_key,
                label=label,
                route=wb_key,
                icon=icon,
                section="plan",
                layout={
                    "blocks": [{"project_block_key": wb_key, "width": "full"}],
                    "nav": nav,
                },
                required_capabilities=[cap],
                orden=100 + i * 10,
                template_slugs=_SCRUM_SLUGS,
                view_type="custom",
            )
        )
    views.append(
        ViewDef(
            key="scrum_metrics",
            label="Métricas",
            route="scrum/metrics",
            icon="line-chart",
            section="plan",
            layout={
                "blocks": [{"project_block_key": "scrum_metrics", "width": "full"}],
                "nav": {
                    "group": "scrum",
                    "group_order": 3,
                    "primary": False,
                },
            },
            required_capabilities=[WORKBENCH_SCRUM_METRICS],
            orden=130,
            template_slugs=_SCRUM_SLUGS,
            view_type="custom",
        )
    )
    ceremony_views = [
        ("scrum_refinement", "Refinement", "scrum/refinement", "list-checks", WORKBENCH_SCRUM_REFINEMENT, 0, True),
        ("scrum_capacity", "Capacity", "scrum/capacity", "gauge", WORKBENCH_SCRUM_CAPACITY, 1, False),
        ("scrum_impediments", "Impedimentos", "scrum/impediments", "alert-triangle", WORKBENCH_SCRUM_IMPEDIMENTS, 2, False),
        ("scrum_daily", "Daily", "scrum/daily", "timer-reset", WORKBENCH_SPRINT_BOARD, 3, False),
        ("scrum_planning_poker", "Planning Poker", "scrum/planning-poker", "dice-5", WORKBENCH_SPRINT_BOARD, 4, False),
        ("scrum_sprint_review", "Sprint Review", "scrum/sprint-review", "messages-square", WORKBENCH_SPRINT_BOARD, 5, False),
        ("scrum_retro", "Retro", "scrum/retro", "repeat", WORKBENCH_SPRINT_BOARD, 6, False),
    ]
    for i, (wb_key, label, route, icon, cap, group_order, is_primary) in enumerate(ceremony_views):
        nav: dict[str, Any] = {
            "group": "ceremonies",
            "group_order": group_order,
            "primary": is_primary,
        }
        if is_primary:
            nav["group_label"] = "Ceremonias"
        views.append(
            ViewDef(
                key=wb_key,
                label=label,
                route=route,
                icon=icon,
                section="plan",
                layout={
                    "blocks": [{"project_block_key": wb_key, "width": "full"}],
                    "nav": nav,
                },
                required_capabilities=[cap],
                orden=200 + i * 10,
                template_slugs=_SCRUM_SLUGS,
                view_type="custom",
            )
        )
    return views


def _software_roles() -> list[PackRoleDef]:
    roles: list[PackRoleDef] = []
    seen: set[str] = set()
    for tpl in PROJECT_TEMPLATES.values():
        for orden, slug in enumerate(tpl.roles, start=1):
            if slug in seen:
                continue
            seen.add(slug)
            caps = sorted(TEMPLATE_ROLE_CAPABILITIES.get(slug, frozenset()))
            template_slugs = [
                t.slug for t in PROJECT_TEMPLATES.values() if slug in t.roles
            ]
            roles.append(
                PackRoleDef(
                    slug=slug,
                    nombre=TEMPLATE_ROLE_LABELS.get(slug, slug),
                    capabilities=caps,
                    is_system=True,
                    orden=orden,
                    template_slugs=template_slugs,
                )
            )
    return roles


def _software_workflow_profiles() -> dict[str, dict[str, dict[str, Any]]]:
    from app.domain.workflow_templates import workflow_for_template
    from app.domain.project_templates import PROJECT_TEMPLATES, SCRUM_TEMPLATE_SLUGS

    waterfall_entities = ("feature", "task", "query", "report", "milestone")
    scrum_entities = ("task", "query", "report", "sprint", "product_backlog")
    profiles: dict[str, dict[str, dict[str, Any]]] = {}
    for template_slug in PROJECT_TEMPLATES:
        entity_types = scrum_entities if template_slug in SCRUM_TEMPLATE_SLUGS else waterfall_entities
        profiles[template_slug] = {
            et: workflow_for_template(template_slug, et)
            for et in entity_types
        }
    return profiles


def pack_software_manifest() -> PackManifest:
    """Alias legacy combinado (deprecated)."""
    return pack_software_manifest_legacy()


def pack_software_manifest_legacy() -> PackManifest:
    from app.services.communication.software_comm_rules import software_communication_rules

    rules = [r.model_dump() for r in software_communication_rules()]
    return PackManifest(
        slug="software",
        nombre="Software Delivery (deprecated)",
        descripcion="Alias legacy — usar software-waterfall o software-scrum.",
        maps_template_slug="t1_cliente_clasico",
        entity_types=_software_entity_types(),
        field_definitions=_software_field_definitions(),
        blocks=_software_blocks(),
        project_views=_software_views(),
        traits={
            "supports_reports": True,
            "supports_external_queries": True,
            "deprecated": True,
        },
        workflow_profiles=_software_workflow_profiles(),
        roles=_software_roles(),
        views=[],
        workflows={},
        workbenches=[],
        communication_rules=rules,
    )


_WATERFALL_ENTITY_KEYS = frozenset({"milestone", "feature", "task", "query", "report"})
_SCRUM_ENTITY_KEYS = frozenset({"task", "query", "report", "sprint", "product_backlog", "impediment"})


def _waterfall_workflow_profiles() -> dict[str, dict[str, dict[str, Any]]]:
    profiles = _software_workflow_profiles()
    return {k: v for k, v in profiles.items() if k not in SCRUM_TEMPLATE_SLUGS}


def _scrum_workflow_profiles() -> dict[str, dict[str, dict[str, Any]]]:
    profiles = _software_workflow_profiles()
    return {k: v for k, v in profiles.items() if k in SCRUM_TEMPLATE_SLUGS}


def pack_software_waterfall_manifest() -> PackManifest:
    from app.services.communication.software_comm_rules import waterfall_communication_rules

    base = pack_software_manifest_legacy()
    rules = [r.model_dump() for r in waterfall_communication_rules()]
    return base.model_copy(
        update={
            "slug": "software-waterfall",
            "nombre": "Software Waterfall",
            "descripcion": "Entrega waterfall: milestone → feature → task, kanban y UAT.",
            "entity_types": [
                e for e in base.entity_types if e.key in _WATERFALL_ENTITY_KEYS
            ],
            "field_definitions": [
                fd
                for fd in base.field_definitions
                if fd.entity_type_key in _WATERFALL_ENTITY_KEYS
            ],
            "project_views": [
                v
                for v in base.project_views
                if not v.template_slugs
                or not set(v.template_slugs).issubset(set(_SCRUM_SLUGS))
            ],
            "workflow_profiles": _waterfall_workflow_profiles(),
            "communication_rules": rules,
            "traits": {
                "supports_reports": True,
                "supports_external_queries": True,
                "delivery_mode": "waterfall",
            },
        }
    )


def pack_software_scrum_manifest() -> PackManifest:
    from app.services.communication.software_comm_rules import scrum_communication_rules

    base = pack_software_manifest_legacy()
    rules = [r.model_dump() for r in scrum_communication_rules()]
    return base.model_copy(
        update={
            "slug": "software-scrum",
            "nombre": "Software Scrum",
            "descripcion": "Entrega Scrum: product backlog, sprints, épicas/historias/dev tasks.",
            "entity_types": [
                e for e in base.entity_types if e.key in _SCRUM_ENTITY_KEYS
            ],
            "field_definitions": [
                fd
                for fd in base.field_definitions
                if fd.entity_type_key in _SCRUM_ENTITY_KEYS
            ],
            "project_views": [
                v
                for v in base.project_views
                if v.template_slugs and set(v.template_slugs).issubset(set(_SCRUM_SLUGS))
            ],
            "workflow_profiles": _scrum_workflow_profiles(),
            "communication_rules": rules,
            "traits": {
                "supports_reports": True,
                "supports_external_queries": True,
                "delivery_mode": "scrum",
            },
        }
    )

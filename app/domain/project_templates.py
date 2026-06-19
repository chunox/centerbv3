"""Catálogo de templates de proyecto al crear (pack software)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException

if TYPE_CHECKING:
    from app.models.entities import Project

ProjectTemplateSlug = Literal[
    "t1_cliente_clasico",
    "t2_cliente_pm_tecnico",
    "t3_interno_clasico",
    "t4_interno_pm_tecnico",
    "t5_freestyle",
    "t6_scrum_interno",
    "t7_scrum_cliente",
]

ProjectTipoFromTemplate = Literal["con_cliente", "interno", "freestyle"]
TemplateDeliveryMode = Literal["waterfall", "scrum"]


@dataclass(frozen=True, slots=True)
class ProjectTemplateDef:
    slug: ProjectTemplateSlug
    nombre: str
    descripcion: str
    tipo: ProjectTipoFromTemplate
    delivery_mode: TemplateDeliveryMode
    roles: tuple[str, ...]
    creator_role: str
    orden: int


PROJECT_TEMPLATES: dict[str, ProjectTemplateDef] = {
    "t1_cliente_clasico": ProjectTemplateDef(
        slug="t1_cliente_clasico",
        nombre="Entrega con cliente",
        descripcion="PM, Tech Líder, Dev, QA y Cliente. Flujo completo con validación externa.",
        tipo="con_cliente",
        delivery_mode="waterfall",
        roles=("pm", "tech_lead", "dev", "qa", "cliente"),
        creator_role="pm",
        orden=1,
    ),
    "t2_cliente_pm_tecnico": ProjectTemplateDef(
        slug="t2_cliente_pm_tecnico",
        nombre="Cliente compacto",
        descripcion="PM Técnico, Dev, QA y Cliente. Gestión y desarrollo en un rol.",
        tipo="con_cliente",
        delivery_mode="waterfall",
        roles=("pm_tecnico", "dev", "qa", "cliente"),
        creator_role="pm_tecnico",
        orden=2,
    ),
    "t3_interno_clasico": ProjectTemplateDef(
        slug="t3_interno_clasico",
        nombre="Squad interno",
        descripcion="PM, Tech Líder, Dev y QA. Sin cliente en el flujo.",
        tipo="interno",
        delivery_mode="waterfall",
        roles=("pm", "tech_lead", "dev", "qa"),
        creator_role="pm",
        orden=3,
    ),
    "t4_interno_pm_tecnico": ProjectTemplateDef(
        slug="t4_interno_pm_tecnico",
        nombre="Interno compacto",
        descripcion="PM Técnico, Dev y QA. Equipo mínimo interno.",
        tipo="interno",
        delivery_mode="waterfall",
        roles=("pm_tecnico", "dev", "qa"),
        creator_role="pm_tecnico",
        orden=4,
    ),
    "t5_freestyle": ProjectTemplateDef(
        slug="t5_freestyle",
        nombre="Flexible",
        descripcion="Los 6 roles. Personalizable en Configuración.",
        tipo="freestyle",
        delivery_mode="waterfall",
        roles=("pm", "pm_tecnico", "dev", "tech_lead", "qa", "cliente"),
        creator_role="pm",
        orden=5,
    ),
    "t6_scrum_interno": ProjectTemplateDef(
        slug="t6_scrum_interno",
        nombre="Scrum Interno",
        descripcion="PM (PO), Tech Líder, Dev y QA. Sprints con Product Backlog. Sin cliente.",
        tipo="interno",
        delivery_mode="scrum",
        roles=("pm", "tech_lead", "dev", "qa"),
        creator_role="pm",
        orden=6,
    ),
    "t7_scrum_cliente": ProjectTemplateDef(
        slug="t7_scrum_cliente",
        nombre="Scrum con Cliente",
        descripcion="PM (PO), Tech Líder, Dev, QA y Cliente. Sprints con validación externa.",
        tipo="con_cliente",
        delivery_mode="scrum",
        roles=("pm", "tech_lead", "dev", "qa", "cliente"),
        creator_role="pm",
        orden=7,
    ),
}

SCRUM_TEMPLATE_SLUGS: frozenset[str] = frozenset(
    slug for slug, tpl in PROJECT_TEMPLATES.items() if tpl.delivery_mode == "scrum"
)

DEFAULT_TEMPLATE_SLUG: ProjectTemplateSlug = "t1_cliente_clasico"


def get_template(slug: str) -> ProjectTemplateDef:
    tpl = PROJECT_TEMPLATES.get(slug)
    if tpl is None:
        raise HTTPException(status_code=422, detail=f"Template de proyecto inválido: {slug}")
    return tpl


def delivery_mode_for_template_slug(template_slug: str | None) -> TemplateDeliveryMode:
    """Delivery waterfall/scrum declarado en la plantilla (default waterfall)."""
    if not template_slug or template_slug in ("default", ""):
        return "waterfall"
    tpl = PROJECT_TEMPLATES.get(template_slug)
    if tpl is None:
        return "waterfall"
    return tpl.delivery_mode


def is_scrum_template_slug(template_slug: str | None) -> bool:
    return delivery_mode_for_template_slug(template_slug) == "scrum"


def project_tipo_for_template(template_slug: str, *, pack_slug: str = "software") -> str:
    if pack_slug != "software" or template_slug in ("default", ""):
        return "interno"
    tpl = PROJECT_TEMPLATES.get(template_slug)
    if tpl is None:
        return "interno"
    if tpl.tipo == "freestyle" and pack_slug != "software":
        return "interno"
    return tpl.tipo


def project_tipo_for_project(project: Project) -> str:
    return project_tipo_for_template(
        project.template_slug or "default",
        pack_slug=project.pack_slug or "software",
    )


def resolve_project_tipo(
    template_slug: str,
    tipo_override: str | None = None,
    *,
    pack_slug: str = "software",
) -> str:
    if tipo_override:
        return tipo_override
    return project_tipo_for_template(template_slug, pack_slug=pack_slug)


def template_slug_for_legacy_tipo(tipo: str) -> str:
    if tipo == "interno":
        return "t3_interno_clasico"
    if tipo == "freestyle":
        return "t5_freestyle"
    return "t1_cliente_clasico"


def list_templates_for_api() -> list[dict]:
    return [
        {
            "slug": t.slug,
            "nombre": t.nombre,
            "descripcion": t.descripcion,
            "tipo": t.tipo,
            "delivery_mode": t.delivery_mode,
            "roles": list(t.roles),
            "creator_role": t.creator_role,
            "orden": t.orden,
        }
        for t in sorted(PROJECT_TEMPLATES.values(), key=lambda x: x.orden)
    ]

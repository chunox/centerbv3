"""Catálogo de templates de proyecto al crear."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException

ProjectTemplateSlug = Literal[
    "t1_cliente_clasico",
    "t2_cliente_pm_tecnico",
    "t3_interno_clasico",
    "t4_interno_pm_tecnico",
    "t5_freestyle",
]

ProjectTipoFromTemplate = Literal["con_cliente", "interno", "freestyle"]


@dataclass(frozen=True, slots=True)
class ProjectTemplateDef:
    slug: ProjectTemplateSlug
    nombre: str
    descripcion: str
    tipo: ProjectTipoFromTemplate
    roles: tuple[str, ...]
    creator_role: str
    orden: int


PROJECT_TEMPLATES: dict[str, ProjectTemplateDef] = {
    "t1_cliente_clasico": ProjectTemplateDef(
        slug="t1_cliente_clasico",
        nombre="Entrega con cliente",
        descripcion="PM, Tech Líder, Dev, QA y Cliente. Flujo completo con validación externa.",
        tipo="con_cliente",
        roles=("pm", "tech_lead", "dev", "qa", "cliente"),
        creator_role="pm",
        orden=1,
    ),
    "t2_cliente_pm_tecnico": ProjectTemplateDef(
        slug="t2_cliente_pm_tecnico",
        nombre="Cliente compacto",
        descripcion="PM Técnico, Dev, QA y Cliente. Gestión y desarrollo en un rol.",
        tipo="con_cliente",
        roles=("pm_tecnico", "dev", "qa", "cliente"),
        creator_role="pm_tecnico",
        orden=2,
    ),
    "t3_interno_clasico": ProjectTemplateDef(
        slug="t3_interno_clasico",
        nombre="Squad interno",
        descripcion="PM, Tech Líder, Dev y QA. Sin cliente en el flujo.",
        tipo="interno",
        roles=("pm", "tech_lead", "dev", "qa"),
        creator_role="pm",
        orden=3,
    ),
    "t4_interno_pm_tecnico": ProjectTemplateDef(
        slug="t4_interno_pm_tecnico",
        nombre="Interno compacto",
        descripcion="PM Técnico, Dev y QA. Equipo mínimo interno.",
        tipo="interno",
        roles=("pm_tecnico", "dev", "qa"),
        creator_role="pm_tecnico",
        orden=4,
    ),
    "t5_freestyle": ProjectTemplateDef(
        slug="t5_freestyle",
        nombre="Freestyle",
        descripcion="Los 6 roles. Personalizable en Configuración.",
        tipo="freestyle",
        roles=("pm", "pm_tecnico", "dev", "tech_lead", "qa", "cliente"),
        creator_role="pm",
        orden=5,
    ),
}

DEFAULT_TEMPLATE_SLUG: ProjectTemplateSlug = "t1_cliente_clasico"


def get_template(slug: str) -> ProjectTemplateDef:
    tpl = PROJECT_TEMPLATES.get(slug)
    if tpl is None:
        raise HTTPException(status_code=422, detail=f"Template de proyecto inválido: {slug}")
    return tpl


def resolve_project_tipo(
    template_slug: str,
    tipo_override: str | None = None,
) -> str:
    tpl = get_template(template_slug)
    if tpl.tipo == "freestyle":
        return "freestyle"
    return tpl.tipo


def template_slug_for_legacy_tipo(tipo: str) -> str:
    if tipo == "interno":
        return "t3_interno_clasico"
    return "t1_cliente_clasico"


def list_templates_for_api() -> list[dict]:
    return [
        {
            "slug": t.slug,
            "nombre": t.nombre,
            "descripcion": t.descripcion,
            "tipo": t.tipo,
            "roles": list(t.roles),
            "creator_role": t.creator_role,
            "orden": t.orden,
        }
        for t in sorted(PROJECT_TEMPLATES.values(), key=lambda x: x.orden)
    ]

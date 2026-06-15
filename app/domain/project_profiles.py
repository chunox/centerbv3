"""Perfiles de espacio/proyecto (reemplazo genérico de project.tipo)."""
from __future__ import annotations

from typing import Literal

ProjectProfileSlug = Literal["with_client", "internal", "flexible", "default"]

PROFILE_WITH_CLIENT: ProjectProfileSlug = "with_client"
PROFILE_INTERNAL: ProjectProfileSlug = "internal"
PROFILE_FLEXIBLE: ProjectProfileSlug = "flexible"
PROFILE_DEFAULT: ProjectProfileSlug = "default"

_TEMPLATE_SLUG_TO_PROFILE: dict[str, str] = {
    "t1_cliente_clasico": PROFILE_WITH_CLIENT,
    "t2_cliente_pm_tecnico": PROFILE_WITH_CLIENT,
    "t3_interno_clasico": PROFILE_INTERNAL,
    "t4_interno_pm_tecnico": PROFILE_INTERNAL,
    "t5_freestyle": PROFILE_FLEXIBLE,
    "t6_scrum_interno": PROFILE_INTERNAL,
    "t7_scrum_cliente": PROFILE_WITH_CLIENT,
}


def template_slug_to_profile(template_slug: str) -> str:
    return _TEMPLATE_SLUG_TO_PROFILE.get(template_slug, PROFILE_DEFAULT)

LEGACY_TIPO_TO_PROFILE: dict[str, ProjectProfileSlug] = {
    "con_cliente": "with_client",
    "interno": "internal",
    "freestyle": "flexible",
}

PROFILE_TO_LEGACY_TIPO: dict[str, str] = {
    "with_client": "con_cliente",
    "internal": "interno",
    "flexible": "freestyle",
    "default": "freestyle",
}


def resolve_profile_slug(
    *,
    pack_slug: str,
    template_profile: str | None = None,
    legacy_tipo: str | None = None,
    profile_override: str | None = None,
) -> str:
    if profile_override:
        return profile_override
    if template_profile:
        return template_profile
    if legacy_tipo:
        if legacy_tipo == "freestyle" and pack_slug != "software":
            return PROFILE_DEFAULT
        return LEGACY_TIPO_TO_PROFILE.get(legacy_tipo, PROFILE_DEFAULT)
    if pack_slug == "software":
        return PROFILE_WITH_CLIENT
    return PROFILE_DEFAULT


def legacy_tipo_from_profile(profile_slug: str, *, pack_slug: str = "software") -> str:
    if profile_slug == PROFILE_DEFAULT and pack_slug != "software":
        return "interno"
    return PROFILE_TO_LEGACY_TIPO.get(profile_slug, "interno")

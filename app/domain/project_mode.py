"""

Modo de delivery del pack software — derivado de la plantilla del proyecto.



Fuente de verdad del valor: `ProjectTemplateDef.delivery_mode` en project_templates.py.

Este módulo expone guards de API y helpers de servicio; no es un tercer nivel de producto.

"""

from __future__ import annotations



from enum import Enum

from typing import TYPE_CHECKING



from app.domain.project_templates import (

    SCRUM_TEMPLATE_SLUGS,

    delivery_mode_for_template_slug,

    is_scrum_template_slug,

)



if TYPE_CHECKING:

    from app.models.entities import Project, ProjectRecord



SCRUM_BLOCKED_RECORD_TYPES = frozenset({"feature", "epic", "milestone"})
WATERFALL_BLOCKED_RECORD_TYPES = frozenset({"sprint", "product_backlog"})

# epic/feature aquí = record_type SQL legacy/incorrecto en Scrum.

# Épicas e historias válidas: task + data.scrum_role (epic | story | dev).

WATERFALL_BLOCKED_SCRUM_ROLES = frozenset({"epic", "story", "dev"})





class SoftwareDeliveryMode(str, Enum):

    WATERFALL = "waterfall"

    SCRUM = "scrum"





def delivery_mode_for_template(template_slug: str | None) -> SoftwareDeliveryMode:

    return SoftwareDeliveryMode(delivery_mode_for_template_slug(template_slug))





def delivery_mode_for_project(project: Project) -> SoftwareDeliveryMode:

    pack = project.pack_slug or "software"

    if pack == "software-scrum":

        return SoftwareDeliveryMode.SCRUM

    if pack == "software-waterfall":

        return SoftwareDeliveryMode.WATERFALL

    if pack != "software":

        return SoftwareDeliveryMode.WATERFALL

    return delivery_mode_for_template(project.template_slug)





def is_scrum_template(template_slug: str | None) -> bool:

    return is_scrum_template_slug(template_slug)





def is_scrum_mode(project: Project) -> bool:

    return delivery_mode_for_project(project) == SoftwareDeliveryMode.SCRUM





def is_waterfall_mode(project: Project) -> bool:

    return delivery_mode_for_project(project) == SoftwareDeliveryMode.WATERFALL





def is_record_type_allowed(

    project: Project,

    record_type: str,

    *,

    data: dict | None = None,

) -> tuple[bool, str | None]:

    mode = delivery_mode_for_project(project)

    if mode == SoftwareDeliveryMode.SCRUM and record_type in SCRUM_BLOCKED_RECORD_TYPES:

        if record_type == "milestone":

            return False, (

                f"Proyecto Scrum ({project.template_slug}): no usar record_type=milestone. "

                "Usá record_type=sprint o product_backlog."

            )

        return False, (

            f"Proyecto Scrum ({project.template_slug}): record_type={record_type!r} no aplica. "

            "Usá record_type=task con data.scrum_role: epic (épica), story (historia) o dev."

        )

    if mode == SoftwareDeliveryMode.WATERFALL:

        if record_type in WATERFALL_BLOCKED_RECORD_TYPES:

            return False, (

                f"Proyecto waterfall ({project.template_slug}): record_type={record_type!r} "

                "es solo Scrum. Jerarquía: milestone → feature → task."

            )

        scrum_role = (data or {}).get("scrum_role")

        if scrum_role in WATERFALL_BLOCKED_SCRUM_ROLES:

            return False, (

                "Proyecto waterfall: no usar data.scrum_role. "

                "Jerarquía: milestone → feature → task."

            )

    return True, None





def is_software_work_item(record: ProjectRecord) -> bool:

    """Ítem de negocio: feature (waterfall) o task story (Scrum)."""

    if record.record_type == "feature":

        return True

    from app.services.scrum_v2_structure import is_scrum_story



    return is_scrum_story(record)





def filter_portfolio_work_items(

    project: Project,

    rows: list[ProjectRecord],

) -> list[ProjectRecord]:

    """Registros que cuentan como 'feature/historia' en portfolio e inbox."""

    if is_scrum_mode(project):

        from app.services.scrum_v2_structure import is_scrum_story



        return [row for row in rows if is_scrum_story(row)]

    return [row for row in rows if row.record_type == "feature"]



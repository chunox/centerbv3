"""
Motor de transiciones de workflow.

Valida que:
  1. La transición existe en el pack para el record_type.
  2. El estado actual está en from_states.
  3. El actor tiene el rol requerido.
  4. Los gates se cumplen (not_blocked, dependency_satisfied).

Si todo OK, aplica el nuevo estado y retorna el record actualizado.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.packs.definitions import get_pack, TEMPLATE_TO_PACK, TransitionDef
from app.models.entities import Project, ProjectRecord
from app.services.access import MemberContext, get_member_context, require_capability
from app.services.blockers import has_active_blocker_on_chain, has_blocked_descendant, has_unsatisfied_dependencies
from app.services.access_context import get_actor_role_slug
from app.services.capability_map import capability_for_transition
from app.services.workflow.errors import WorkflowError
from app.services.workflow.movement_rules import assert_movement_allowed
from app.services.workflow.side_effects import apply_side_effects


def _get_transition(
    pack_key: str,
    entity_type: str,
    action_id: str,
    project_settings: dict,
    current_status: str | None = None,
) -> TransitionDef:
    pack = get_pack(pack_key)
    if not pack:
        raise WorkflowError("Pack no encontrado")

    # Resolver workflow activo (puede ser variant)
    variant_key = (project_settings or {}).get(f"{entity_type}_workflow")
    variant_full = f"{entity_type}.{variant_key}" if variant_key else ""
    wf = pack.workflow_variants.get(variant_full, None) if variant_key else None
    if wf is None:
        wf = pack.workflows.get(entity_type)
    if wf is None:
        raise WorkflowError(f"No hay workflow definido para '{entity_type}'")

    matches = [t for t in wf.transitions if t.action_id == action_id]
    if not matches:
        raise WorkflowError(f"Acción '{action_id}' no existe en el workflow de '{entity_type}'")
    if current_status is not None:
        for t in matches:
            if current_status in t.from_states:
                return t
    return matches[0]


def _check_gates(db: Session, record: ProjectRecord, transition: TransitionDef) -> None:
    for gate in transition.gates:
        if gate == "not_blocked":
            if has_active_blocker_on_chain(db, record):
                raise WorkflowError("El record tiene bloqueadores activos sin resolver (propio o heredado)")

        elif gate == "dependency_satisfied":
            if has_unsatisfied_dependencies(db, record):
                raise WorkflowError("Hay dependencias previas sin completar")

        elif gate == "sprint_assigned":
            from app.services.scrum.sprint_membership import is_epic_in_sprint, parent_is_sprint

            role = (record.extra or {}).get("scrum_role")
            if role == "story" and not parent_is_sprint(db, record.parent_id):
                raise WorkflowError("La historia no tiene sprint asignado")
            if role == "epic" and not is_epic_in_sprint(record):
                raise WorkflowError("La épica no tiene sprint asignado")

        elif gate == "not_blocked_descendant":
            if has_blocked_descendant(db, record):
                raise WorkflowError(
                    "No se puede reabrir: hay descendientes en estado bloqueado."
                )


def _resolve_entity_type(record: ProjectRecord, pack_key: str) -> str:
    """
    Resuelve el entity_type para buscar el workflow.
    Scrum guarda todos los records con record_type='task' + extra.scrum_role.
    Si no hay workflow para el record_type directamente, intenta con scrum_role.
    """
    from app.domain.packs.definitions import PACK_DEFINITIONS

    _SCRUM_ROLE_ENTITY = {
        "epic": "epic",
        "story": "story",
        "dev": "dev_task",
        "subtask": "subtask",
    }

    pack = PACK_DEFINITIONS.get(pack_key)
    if pack and record.record_type not in pack.workflows:
        scrum_role = (record.extra or {}).get("scrum_role")
        if scrum_role:
            entity = _SCRUM_ROLE_ENTITY.get(scrum_role, scrum_role)
            if entity in pack.workflows:
                return entity
    return record.record_type


def apply_transition(
    db: Session,
    project: Project,
    record: ProjectRecord,
    action_id: str,
    actor_id: str,
    member_ctx: MemberContext | None = None,
) -> ProjectRecord:
    """Aplica la transición y persiste el nuevo estado."""
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    settings: dict = project.settings or {}

    entity_type = _resolve_entity_type(record, pack_key)
    transition = _get_transition(pack_key, entity_type, action_id, settings, record.status)

    # Verificar estado actual
    if record.status not in transition.from_states:
        raise WorkflowError(
            f"Estado actual '{record.status}' no permite la acción '{action_id}'. "
            f"Estados válidos: {list(transition.from_states)}"
        )

    ctx = member_ctx or get_member_context(db, actor_id, str(project.id))

    # Verificar rol (cualquiera de los roles del actor puede satisfacer)
    if transition.required_roles:
        actor_roles = ctx.role_slugs if ctx else set()
        if not actor_roles and ctx:
            actor_roles = {ctx.role_slug}
        if not actor_roles:
            actor_roles = {get_actor_role_slug(db, str(project.id), actor_id) or ""}
        if not actor_roles.intersection(transition.required_roles):
            primary = next(iter(actor_roles), "unknown")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tu rol '{primary}' no puede ejecutar esta acción",
            )

    # Verificar capability
    if ctx:
        trans_cap = capability_for_transition(entity_type, action_id)
        if trans_cap:
            require_capability(ctx, trans_cap)

    # Regla global de bloqueos (antes de gates por transición)
    assert_movement_allowed(db, record, action_id)

    # Verificar gates
    _check_gates(db, record, transition)

    # Aplicar transición
    record.status = transition.to_state
    db.flush()

    # Side effects declarados en el pack
    if transition.side_effects:
        apply_side_effects(db, transition.side_effects, record, project)

    return record

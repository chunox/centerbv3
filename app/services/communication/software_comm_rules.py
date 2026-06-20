"""Reglas de comunicación por defecto del pack software (query, report, feature)."""
from __future__ import annotations

from app.domain.capabilities import WORKBENCH_INBOX_CLIENT, WORKBENCH_INBOX_DEV, WORKBENCH_INBOX_PM
from app.schemas.communication_rules import CommunicationRule


def _delivery(
    *,
    recipient_type: str,
    recipient_value: str | None,
    tipo: str,
    workbench_key: str,
    match_states: list[str] | None = None,
) -> dict:
    d: dict = {
        "recipients": {"type": recipient_type, "value": recipient_value},
        "notification": {"tipo": tipo},
        "deep_link": {"workbench_key": workbench_key},
    }
    if match_states:
        d["match_states"] = match_states
    return d


def software_transition_rules() -> list[CommunicationRule]:
    """Reglas on_transition equivalentes a feature_queries._apply_query_capability_side_effects."""
    rules: list[dict] = [
        {
            "id": "query_solicitar_envio_pm_approval",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "solicitar_envio",
                "to_state": "pendiente_aprobacion_pm",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_pendiente_aprobacion",
                    workbench_key="inbox_pm",
                ),
            ],
        },
        {
            "id": "query_solicitar_envio_pm_direct",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "solicitar_envio",
                "to_state": "esperando_pm",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_creada",
                    workbench_key="inbox_pm",
                ),
            ],
        },
        {
            "id": "query_aprobar_envio_client",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "aprobar_envio",
                "to_state": "esperando_cliente",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_CLIENT,
                    tipo="query_creada",
                    workbench_key="inbox_client",
                ),
            ],
        },
        {
            "id": "query_activar_client",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "activar",
                "to_state": "esperando_cliente",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_CLIENT,
                    tipo="query_creada",
                    workbench_key="inbox_client",
                ),
            ],
        },
        {
            "id": "query_activar_cliente_alias",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "activar_cliente",
                "to_state": "esperando_cliente",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_CLIENT,
                    tipo="query_creada",
                    workbench_key="inbox_client",
                ),
            ],
        },
        {
            "id": "query_activar_pm",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "activar",
                "to_state": "esperando_pm",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_creada",
                    workbench_key="inbox_pm",
                ),
            ],
        },
        {
            "id": "query_activar_interno",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "activar_interno",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_creada",
                    workbench_key="inbox_pm",
                ),
            ],
        },
        {
            "id": "query_responder",
            "event": "on_transition",
            "match": {"entity_type": "query", "action_id": "responder"},
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_respondida",
                    workbench_key="inbox_pm",
                ),
                _delivery(
                    recipient_type="author",
                    recipient_value=None,
                    tipo="query_respondida",
                    workbench_key="inbox_dev",
                ),
            ],
        },
        {
            "id": "query_cerrar_validar",
            "event": "on_transition",
            "match": {"entity_type": "query", "action_id": "validar_aceptar"},
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_respondida",
                    workbench_key="inbox_pm",
                ),
                _delivery(
                    recipient_type="author",
                    recipient_value=None,
                    tipo="query_respondida",
                    workbench_key="inbox_dev",
                ),
            ],
        },
        {
            "id": "query_cerrar_pm",
            "event": "on_transition",
            "match": {"entity_type": "query", "action_id": "cerrar"},
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_respondida",
                    workbench_key="inbox_pm",
                ),
                _delivery(
                    recipient_type="author",
                    recipient_value=None,
                    tipo="query_respondida",
                    workbench_key="inbox_dev",
                ),
            ],
        },
        {
            "id": "query_cerrar_directo",
            "event": "on_transition",
            "match": {"entity_type": "query", "action_id": "cerrar_directo"},
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_PM,
                    tipo="query_respondida",
                    workbench_key="inbox_pm",
                ),
                _delivery(
                    recipient_type="author",
                    recipient_value=None,
                    tipo="query_respondida",
                    workbench_key="inbox_dev",
                ),
            ],
        },
        {
            "id": "query_validar_rechazar",
            "event": "on_transition",
            "match": {
                "entity_type": "query",
                "action_id": "validar_rechazar",
                "to_state": "esperando_cliente",
            },
            "deliveries": [
                _delivery(
                    recipient_type="capability",
                    recipient_value=WORKBENCH_INBOX_CLIENT,
                    tipo="query_creada",
                    workbench_key="inbox_client",
                ),
            ],
        },
        {
            "id": "query_rechazar",
            "event": "on_transition",
            "match": {"entity_type": "query", "action_id": "rechazar"},
            "deliveries": [
                _delivery(
                    recipient_type="author",
                    recipient_value=None,
                    tipo="query_rechazada",
                    workbench_key="inbox_dev",
                ),
            ],
        },
    ]
    return [CommunicationRule.model_validate(r) for r in rules]


def software_record_created_rules() -> list[CommunicationRule]:
    return [
        CommunicationRule.model_validate(
            {
                "id": "report_created_pm",
                "enabled": True,
                "event": "on_record_created",
                "match": {"record_type": "report"},
                "deliveries": [
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_PM,
                        tipo="reporte_recibido",
                        workbench_key="inbox_pm",
                    ),
                ],
            }
        ),
    ]


def software_state_entered_rules() -> list[CommunicationRule]:
    return [
        CommunicationRule.model_validate(
            {
                "id": "feature_blocked",
                "enabled": True,
                "event": "on_state_entered",
                "match": {"entity_type": "feature", "to_state": "bloqueada"},
                "deliveries": [
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_PM,
                        tipo="feature_bloqueada",
                        workbench_key="inbox_pm",
                    ),
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_DEV,
                        tipo="feature_bloqueada",
                        workbench_key="inbox_dev",
                    ),
                ],
            }
        ),
        CommunicationRule.model_validate(
            {
                "id": "feature_unblocked",
                "enabled": True,
                "event": "on_state_entered",
                "match": {"entity_type": "feature", "to_state": "desbloqueada"},
                "deliveries": [
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_PM,
                        tipo="feature_desbloqueada",
                        workbench_key="inbox_pm",
                    ),
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_DEV,
                        tipo="feature_desbloqueada",
                        workbench_key="inbox_dev",
                    ),
                ],
            }
        ),
        CommunicationRule.model_validate(
            {
                "id": "story_blocked",
                "enabled": True,
                "event": "on_state_entered",
                "match": {
                    "entity_type": "task",
                    "to_state": "bloqueada",
                    "scrum_role": "story",
                },
                "deliveries": [
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_PM,
                        tipo="feature_bloqueada",
                        workbench_key="inbox_pm",
                    ),
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_DEV,
                        tipo="feature_bloqueada",
                        workbench_key="inbox_dev",
                    ),
                ],
            }
        ),
        CommunicationRule.model_validate(
            {
                "id": "story_unblocked",
                "enabled": True,
                "event": "on_state_entered",
                "match": {
                    "entity_type": "task",
                    "to_state": "desbloqueada",
                    "scrum_role": "story",
                },
                "deliveries": [
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_PM,
                        tipo="feature_desbloqueada",
                        workbench_key="inbox_pm",
                    ),
                    _delivery(
                        recipient_type="capability",
                        recipient_value=WORKBENCH_INBOX_DEV,
                        tipo="feature_desbloqueada",
                        workbench_key="inbox_dev",
                    ),
                ],
            }
        ),
    ]


def software_communication_rules() -> list[CommunicationRule]:
    from app.services.communication.legacy_defaults import comment_communication_rules

    return (
        comment_communication_rules()
        + software_transition_rules()
        + software_record_created_rules()
        + software_state_entered_rules()
    )


_SCRUM_ONLY_RULE_IDS = frozenset({"story_blocked", "story_unblocked"})


def waterfall_communication_rules() -> list[CommunicationRule]:
    return [r for r in software_communication_rules() if r.id not in _SCRUM_ONLY_RULE_IDS]


def scrum_communication_rules() -> list[CommunicationRule]:
    return software_communication_rules()

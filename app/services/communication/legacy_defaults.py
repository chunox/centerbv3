"""Reglas por defecto equivalentes al hardcode legacy (software pack)."""
from __future__ import annotations

from app.schemas.communication_rules import CommunicationRule


def comment_communication_rules() -> list[CommunicationRule]:
    return [
        CommunicationRule.model_validate(
            {
                "id": "comment_query_report",
                "enabled": True,
                "event": "on_comment",
                "match": {"comment_entity_type": "feature_query"},
                "deliveries": [
                    {
                        "recipients": {"type": "capability", "value": "workbench.inbox.pm"},
                        "notification": {"tipo": "comentario_nuevo"},
                        "deep_link": {"workbench_key": "inbox_pm"},
                    },
                    {
                        "recipients": {"type": "author"},
                        "notification": {"tipo": "comentario_nuevo"},
                        "deep_link": {"workbench_key": "inbox_dev"},
                    },
                    {
                        "recipients": {
                            "type": "capability",
                            "value": "workbench.inbox.client",
                        },
                        "notification": {"tipo": "comentario_nuevo"},
                        "deep_link": {"workbench_key": "inbox_client"},
                        "match_states": ["esperando_cliente", "respuesta_cliente"],
                    },
                ],
            }
        ),
        CommunicationRule.model_validate(
            {
                "id": "comment_feature_report",
                "enabled": True,
                "event": "on_comment",
                "match": {"comment_entity_type": "feature_report"},
                "deliveries": [
                    {
                        "recipients": {"type": "capability", "value": "workbench.inbox.pm"},
                        "notification": {"tipo": "comentario_nuevo"},
                        "deep_link": {"workbench_key": "inbox_pm"},
                    },
                    {
                        "recipients": {"type": "record_field", "value": "reported_by"},
                        "notification": {"tipo": "comentario_nuevo"},
                        "deep_link": {"workbench_key": "inbox_client"},
                    },
                ],
            }
        ),
    ]


def default_communication_rules() -> list[CommunicationRule]:
    from app.services.communication.software_comm_rules import software_communication_rules

    return software_communication_rules()


def default_communication_rules_for_pack(pack_slug: str | None) -> list[CommunicationRule]:
    if pack_slug == "marketing360":
        from app.services.communication.marketing360_comm_rules import (
            marketing360_communication_rules,
        )

        return marketing360_communication_rules()
    if pack_slug == "creativo":
        from app.services.communication.creativo_comm_rules import creativo_communication_rules

        return creativo_communication_rules()
    return default_communication_rules()

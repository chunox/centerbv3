"""Reglas de comunicación por defecto del pack marketing360."""
from __future__ import annotations

from app.domain.capabilities import WORKBENCH_INBOX_CLIENT, WORKBENCH_INBOX_PM
from app.schemas.communication_rules import CommunicationRule
from app.services.communication.software_comm_rules import software_communication_rules


def marketing360_communication_rules() -> list[CommunicationRule]:
    base = software_communication_rules()
    extra = CommunicationRule.model_validate(
        {
            "id": "pieza_esperando_aprobacion",
            "enabled": True,
            "event": "on_state_entered",
            "match": {"entity_type": "pieza", "to_state": "esperando_aprobacion"},
            "deliveries": [
                {
                    "recipients": {
                        "type": "capability",
                        "value": WORKBENCH_INBOX_CLIENT,
                    },
                    "notification": {"tipo": "estado_changed"},
                    "deep_link": {"workbench_key": "aprobaciones"},
                },
                {
                    "recipients": {
                        "type": "capability",
                        "value": WORKBENCH_INBOX_PM,
                    },
                    "notification": {"tipo": "estado_changed"},
                    "deep_link": {"workbench_key": "aprobaciones"},
                },
            ],
        }
    )
    return base + [extra]

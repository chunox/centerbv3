"""Reglas de comunicación por defecto del pack creativo."""
from __future__ import annotations

from app.schemas.communication_rules import CommunicationRule
from app.services.communication.software_comm_rules import software_communication_rules


def creativo_communication_rules() -> list[CommunicationRule]:
    return software_communication_rules()

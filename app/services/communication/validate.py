"""Validación de reglas de comunicación."""
from __future__ import annotations

from fastapi import HTTPException

from typing import get_args

from app.schemas.communication_rules import CommunicationRule
from app.services.notifications import NotificationTipo


_VALID_TIPOS = set(get_args(NotificationTipo))


def validate_communication_rules(rules: list[CommunicationRule]) -> None:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for rule in rules:
        if not rule.id:
            errors.append("Regla sin id")
            continue
        if rule.id in seen_ids:
            errors.append(f"Id duplicado: {rule.id}")
        seen_ids.add(rule.id)
        if not rule.deliveries:
            errors.append(f"Regla '{rule.id}' sin deliveries")
        for delivery in rule.deliveries:
            tipo = (delivery.notification or {}).get("tipo")
            if tipo and tipo not in _VALID_TIPOS:
                errors.append(f"Regla '{rule.id}': tipo '{tipo}' inválido")
    if errors:
        raise HTTPException(status_code=422, detail={"communication_rules": errors})

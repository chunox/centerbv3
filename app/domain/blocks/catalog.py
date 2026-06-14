"""Catálogo global de bloques reutilizables."""
from __future__ import annotations

from typing import Any

SYSTEM_BLOCKS: dict[str, dict[str, Any]] = {
    "overview": {
        "nombre": "Resumen",
        "descripcion": "Dashboard de proyecto",
        "manifest": {"view_type": "overview"},
        "orden": 10,
    },
    "inbox": {
        "nombre": "Bandeja",
        "descripcion": "Cola de acciones por rol",
        "manifest": {"view_type": "inbox"},
        "orden": 20,
    },
    "kanban": {
        "nombre": "Kanban",
        "descripcion": "Tablero por estados",
        "manifest": {"view_type": "board", "required_traits": ["kanban"]},
        "orden": 30,
    },
    "board": {
        "nombre": "Tablero",
        "descripcion": "Tablero genérico por estados de registro",
        "manifest": {"view_type": "board"},
        "orden": 35,
    },
    "scope": {
        "nombre": "Alcance",
        "descripcion": "Jerarquía milestone/feature",
        "manifest": {"view_type": "scope"},
        "orden": 40,
    },
    "hub": {
        "nombre": "Centro del proyecto",
        "descripcion": "Hub y documentación",
        "manifest": {"view_type": "hub"},
        "orden": 60,
    },
    "timeline": {
        "nombre": "Cronograma",
        "descripcion": "Timeline de entregas",
        "manifest": {"view_type": "timeline", "required_traits": ["schedulable"]},
        "orden": 70,
    },
    "activity": {
        "nombre": "Actividad",
        "descripcion": "Auditoría y eventos",
        "manifest": {"view_type": "activity"},
        "orden": 80,
    },
    "team": {
        "nombre": "Equipo",
        "descripcion": "Estado y asignaciones por miembro",
        "manifest": {"view_type": "team"},
        "orden": 75,
    },
    "settings": {
        "nombre": "Configuración",
        "descripcion": "Ajustes del proyecto",
        "manifest": {"view_type": "settings"},
        "orden": 90,
    },
    "studio": {
        "nombre": "Studio",
        "descripcion": "Personalización de flujos, roles y menú",
        "manifest": {"view_type": "studio"},
        "orden": 85,
    },
    "gantt": {
        "nombre": "Gantt",
        "descripcion": "Diagrama de Gantt",
        "manifest": {"view_type": "gantt", "required_traits": ["schedulable"]},
        "orden": 100,
    },
    "checklist": {
        "nombre": "Checklist",
        "descripcion": "Lista de tareas",
        "manifest": {"view_type": "checklist"},
        "orden": 110,
    },
    "uat": {
        "nombre": "Validación UAT",
        "descripcion": "Cola UAT",
        "manifest": {"view_type": "uat"},
        "orden": 120,
    },
    "custom": {
        "nombre": "Vista custom",
        "descripcion": "Vista específica de pack (frontend registry)",
        "manifest": {"view_type": "custom"},
        "orden": 5,
    },
}

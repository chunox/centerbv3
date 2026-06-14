"""Genera reglas de comunicación por defecto para proyectos existentes."""
from __future__ import annotations

import json
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.entities import Project, ProjectCommunicationRules
from app.services.communication.legacy_defaults import default_communication_rules_for_pack


def main() -> None:
    session = SessionLocal()
    try:
        projects = list(session.scalars(select(Project)))
        created = 0
        for project in projects:
            existing = session.scalar(
                select(ProjectCommunicationRules).where(
                    ProjectCommunicationRules.project_id == project.id
                )
            )
            if existing is not None:
                continue
            rules = default_communication_rules_for_pack(project.pack_slug)
            row = ProjectCommunicationRules(
                project_id=project.id,
                definition=json.dumps([r.model_dump() for r in rules], ensure_ascii=False),
            )
            session.add(row)
            created += 1
        session.commit()
        print(f"Seeded communication rules for {created} projects.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
    sys.exit(0)

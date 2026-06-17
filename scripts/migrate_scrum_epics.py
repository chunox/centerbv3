"""
Migra proyectos Scrum (t6/t7) legacy (parent_id → milestone) al modelo epic + sprint_id.

NO ejecutar en proyectos creados con seed_scrum_pack.py o seeds post-épica.

Uso (con venv activado o ruta explícita):

  .venv\\Scripts\\python.exe scripts/migrate_scrum_epics.py

Idempotente: puede ejecutarse varias veces.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.models.entities import Project, ProjectRecord
from app.services.records.repository import update_record_fields
from app.services.scrum_effort import SCRUM_TEMPLATE_SLUGS
from app.services.scrum_structure import apply_scrum_structure


DEFAULT_EPIC_TITLE = "General"


def _ensure_default_epic(db, project: Project, pm_id) -> ProjectRecord:
    epic = db.scalar(
        select(ProjectRecord).where(
            ProjectRecord.project_id == project.id,
            ProjectRecord.record_type == "epic",
        )
    )
    if epic:
        return epic
    epic = ProjectRecord(
        project_id=project.id,
        record_type="epic",
        titulo=DEFAULT_EPIC_TITLE,
        estado="pendiente",
        created_by=pm_id,
        data={},
    )
    db.add(epic)
    db.flush()
    return epic


def migrate_project(db, project: Project) -> dict[str, int]:
    apply_scrum_structure(db, project)
    pm_id = project.created_by
    default_epic = _ensure_default_epic(db, project, pm_id)

    milestones = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "milestone",
            )
        )
    )
    milestone_ids = {m.id for m in milestones}
    epic_ids = {
        e.id
        for e in db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "epic",
            )
        )
    }

    features = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "feature",
            )
        )
    )

    migrated = 0
    for feature in features:
        data = dict(feature.data or {})
        changed = False

        if feature.parent_id in epic_ids:
            pass
        elif feature.parent_id in milestone_ids:
            old_sprint_id = feature.parent_id
            if feature.estado != "product_backlog":
                data["sprint_id"] = str(old_sprint_id)
                changed = True
            feature.parent_id = default_epic.id
            changed = True
        elif feature.parent_id is None:
            feature.parent_id = default_epic.id
            changed = True

        if "story_points" in data:
            data.pop("story_points", None)
            changed = True

        if changed:
            feature.data = data
            migrated += 1

    for sprint in milestones:
        data = dict(sprint.data or {})
        if "velocidad_planeada" in data and "horas_planeadas" not in data:
            data["horas_planeadas"] = data.pop("velocidad_planeada")
            sprint.data = data
        if "velocidad_real" in data and "horas_completadas" not in data:
            data["horas_completadas"] = data.pop("velocidad_real")
            sprint.data = data

    db.flush()
    return {"features": migrated, "sprints": len(milestones)}


def main() -> None:
    db = SessionLocal()
    try:
        projects = list(
            db.scalars(
                select(Project).where(
                    Project.template_slug.in_(tuple(SCRUM_TEMPLATE_SLUGS))
                )
            )
        )
        if not projects:
            print("No hay proyectos Scrum (t6/t7).")
            return
        for project in projects:
            stats = migrate_project(db, project)
            print(f"  {project.nombre}: {stats['features']} historias migradas")
        db.commit()
        print("Migración completada.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""
Asegura vistas board en proyectos genéricos y agrega registros demo para el kanban.

Uso:
  .venv\\Scripts\\python.exe scripts/seed_kanban_board_demo.py
"""
from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.packs.manifest import BlockDef, ViewDef
from app.models.entities import Project, ProjectBlock, ProjectRecord, User
from app.services.blocks import ensure_block_catalog
from app.services.generic_enrichment import add_block_and_view, ensure_role_capabilities
from app.services.records.generic_store import create_record, transition_record

TARGETS = {
    "Conferencia Producto 2026": ("evento", "tarea", "coordinador"),
    "Campaña Verano Creativo": ("creativo", "entregable", "pm"),
    "Consultoría ONG Demo": ("simple", "tarea", "owner"),
}


def _has_board(db, project_id: uuid.UUID, entity_type: str) -> bool:
    rows = db.scalars(
        select(ProjectBlock).where(
            ProjectBlock.project_id == project_id,
            ProjectBlock.enabled.is_(True),
        )
    )
    for row in rows:
        cfg = row.config or {}
        if cfg.get("view_type") == "board" and cfg.get("entity_type_key") == entity_type:
            return True
    return False


def ensure_board(
    db,
    project: Project,
    *,
    entity_type: str,
    role_slug: str,
    key: str = "board",
    label: str = "Tablero",
    route: str = "v/board",
    orden: int = 5,
) -> bool:
    if _has_board(db, project.id, entity_type):
        return False
    ensure_role_capabilities(db, project.id, role_slug, ["workbench.board"])
    add_block_and_view(
        db,
        project,
        block=BlockDef(
            block_slug="board",
            key=key,
            label=label,
            config={"view_type": "board", "entity_type_key": entity_type},
            orden=orden,
        ),
        view=ViewDef(
            key=key,
            label=label,
            route=route,
            icon="columns-3",
            section="plan",
            layout={"blocks": [{"project_block_key": key, "width": "full"}]},
            required_capabilities=["workbench.board"],
            orden=orden,
            view_type="board",
            entity_type=entity_type,
        ),
    )
    return True


def _root_id(db, project_id: uuid.UUID, record_type: str) -> uuid.UUID | None:
    row = db.scalar(
        select(ProjectRecord.id).where(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == record_type,
        ).limit(1)
    )
    return row


def seed_evento_tasks(db, project: Project, pm_id: uuid.UUID, parent_id: uuid.UUID) -> int:
    demos = [
        ("Montaje escenario principal", "iniciar"),
        ("Prueba de sonido", None),
        ("Coordinación prensa", "iniciar"),
        ("Welcome kit speakers", None),
        ("Control de accesos VIP", "iniciar"),
        ("Backup de streaming", None),
    ]
    created = 0
    for titulo, action in demos:
        exists = db.scalar(
            select(ProjectRecord.id).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "tarea",
                ProjectRecord.titulo == titulo,
            )
        )
        if exists:
            continue
        dto = create_record(
            db,
            project,
            record_type="tarea",
            titulo=titulo,
            created_by=pm_id,
            parent_id=parent_id,
            data={"proveedor": "Demo Kanban"},
        )
        rec = db.get(ProjectRecord, dto.id)
        if action == "iniciar" and rec:
            transition_record(
                db, project, rec, action_id="iniciar", actor_user_id=pm_id
            )
        created += 1
    return created


def seed_creativo_entregables(db, project: Project, pm_id: uuid.UUID, parent_id: uuid.UUID) -> int:
    demos = [
        ("Spot TV 15s — storyboard", "enviar_revision"),
        ("Banner display 728x90", None),
        ("Post Instagram carrusel", "enviar_revision"),
        ("Landing promo verano", "enviar_revision"),
        ("Key visual campaña", None),
    ]
    created = 0
    for titulo, action in demos:
        exists = db.scalar(
            select(ProjectRecord.id).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "entregable",
                ProjectRecord.titulo == titulo,
            )
        )
        if exists:
            continue
        dto = create_record(
            db,
            project,
            record_type="entregable",
            titulo=titulo,
            created_by=pm_id,
            parent_id=parent_id,
            data={"version": 1, "canal": "digital"},
        )
        rec = db.get(ProjectRecord, dto.id)
        if action and rec:
            transition_record(
                db, project, rec, action_id=action, actor_user_id=pm_id
            )
        created += 1
    return created


def seed_simple_tareas(db, project: Project, pm_id: uuid.UUID) -> int:
    fases = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "fase",
            )
        )
    )
    if not fases:
        return 0
    demos = [
        ("Entrevistas stakeholders", "iniciar"),
        ("Mapa de procesos AS-IS", None),
        ("Workshop priorización", "iniciar"),
        ("Informe recomendaciones", None),
    ]
    created = 0
    today = date.today()
    for i, (titulo, action) in enumerate(demos):
        exists = db.scalar(
            select(ProjectRecord.id).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "tarea",
                ProjectRecord.titulo == titulo,
            )
        )
        if exists:
            continue
        fase = fases[i % len(fases)]
        dto = create_record(
            db,
            project,
            record_type="tarea",
            titulo=titulo,
            created_by=pm_id,
            parent_id=fase.id,
            fecha_fin=today + timedelta(days=7 + i * 3),
            data={"horas": 4 + i},
        )
        rec = db.get(ProjectRecord, dto.id)
        if action and rec:
            transition_record(
                db, project, rec, action_id=action, actor_user_id=pm_id
            )
        created += 1
    return created


def main() -> int:
    with SessionLocal() as db:
        ensure_block_catalog(db)
        pm = db.scalar(select(User).where(User.email == "pm@center.demo"))
        if pm is None:
            print("No existe pm@center.demo — corré reset_and_seed_demo.py primero.")
            return 1

        for nombre, (pack, entity_type, role_slug) in TARGETS.items():
            project = db.scalar(
                select(Project).where(Project.nombre == nombre, Project.pack_slug == pack)
            )
            if project is None:
                print(f"[skip] No encontrado: {nombre}")
                continue

            board_added = ensure_board(
                db,
                project,
                entity_type=entity_type,
                role_slug=role_slug,
                key="board" if pack != "simple" else "tablero_tareas",
                label="Tablero" if pack != "simple" else "Tablero tareas",
                route="v/board" if pack != "simple" else "v/tablero",
                orden=5 if pack != "simple" else 15,
            )

            root_type = {"evento": "evento", "creativo": "campana", "simple": "fase"}.get(pack)
            root_id = _root_id(db, project.id, root_type) if root_type != "fase" else None

            if pack == "evento" and root_id:
                n = seed_evento_tasks(db, project, pm.id, root_id)
            elif pack == "creativo" and root_id:
                n = seed_creativo_entregables(db, project, pm.id, root_id)
            elif pack == "simple":
                n = seed_simple_tareas(db, project, pm.id)
            else:
                n = 0

            db.commit()
            print(
                f"[ok] {nombre}: board={'añadido' if board_added else 'ya existía'}, "
                f"+{n} registros demo"
            )

    print("\nListo — recarga el frontend. Proyectos demo (login pm@center.demo / demo12345):")
    for nombre in TARGETS:
        print(f"  - {nombre} -> menu Tablero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

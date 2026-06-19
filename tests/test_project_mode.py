"""Guards de modo software: waterfall vs Scrum."""
from __future__ import annotations

import uuid

import pytest

from app.domain.project_mode import (
    SoftwareDeliveryMode,
    delivery_mode_for_template,
    is_record_type_allowed,
    is_scrum_mode,
)
from app.domain.project_templates import (
    PROJECT_TEMPLATES,
    SCRUM_TEMPLATE_SLUGS,
    delivery_mode_for_template_slug,
)
from app.models.entities import Project


def test_delivery_mode_by_template():
    assert delivery_mode_for_template("t1_cliente_clasico") == SoftwareDeliveryMode.WATERFALL
    assert delivery_mode_for_template("t6_scrum_interno") == SoftwareDeliveryMode.SCRUM
    assert delivery_mode_for_template_slug("t7_scrum_cliente") == "scrum"
    assert SCRUM_TEMPLATE_SLUGS == frozenset(
        slug for slug, tpl in PROJECT_TEMPLATES.items() if tpl.delivery_mode == "scrum"
    )


def test_scrum_blocks_epic_record_type_but_allows_task_with_scrum_role():
    project = Project(
        id=uuid.uuid4(),
        nombre="X",
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ok, _ = is_record_type_allowed(project, "epic")
    assert not ok
    ok, _ = is_record_type_allowed(project, "task", data={"scrum_role": "epic"})
    assert ok
    project = Project(
        id=uuid.uuid4(),
        nombre="X",
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ok, msg = is_record_type_allowed(project, "feature")
    assert not ok
    assert "scrum_role" in (msg or "").lower()


def test_waterfall_blocks_scrum_role_on_task():
    project = Project(
        id=uuid.uuid4(),
        nombre="X",
        template_slug="t3_interno_clasico",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ok, msg = is_record_type_allowed(project, "task", data={"scrum_role": "story"})
    assert not ok


def test_waterfall_allows_feature():
    project = Project(
        id=uuid.uuid4(),
        nombre="X",
        template_slug="t3_interno_clasico",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ok, _ = is_record_type_allowed(project, "feature")
    assert ok


def test_scrum_blocks_milestone_record_type():
    project = Project(
        id=uuid.uuid4(),
        nombre="S",
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ok, msg = is_record_type_allowed(project, "milestone")
    assert not ok
    assert "sprint" in (msg or "").lower()
    ok, _ = is_record_type_allowed(project, "sprint")
    assert ok
    ok, _ = is_record_type_allowed(project, "product_backlog")
    assert ok


def test_waterfall_blocks_sprint_record_type():
    project = Project(
        id=uuid.uuid4(),
        nombre="W",
        template_slug="t3_interno_clasico",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ok, msg = is_record_type_allowed(project, "sprint")
    assert not ok
    assert "waterfall" in (msg or "").lower()


def test_is_scrum_mode():
    p = Project(
        id=uuid.uuid4(),
        nombre="S",
        template_slug="t7_scrum_cliente",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    assert is_scrum_mode(p)


def test_is_software_work_item():
    from app.domain.project_mode import is_software_work_item, filter_portfolio_work_items
    from app.models.entities import ProjectRecord

    feature = ProjectRecord(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        record_type="feature",
        titulo="F",
        estado="en_progreso",
        data={},
    )
    story = ProjectRecord(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        record_type="task",
        titulo="H",
        estado="en_progreso",
        data={"scrum_role": "story"},
    )
    dev = ProjectRecord(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        record_type="task",
        titulo="T",
        estado="in_progress",
        data={"scrum_role": "dev"},
    )
    assert is_software_work_item(feature)
    assert is_software_work_item(story)
    assert not is_software_work_item(dev)

    project = Project(
        id=uuid.uuid4(),
        nombre="S",
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio="2026-01-01",
        fecha_fin="2026-12-31",
        organization_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    scoped = filter_portfolio_work_items(project, [feature, story, dev])
    assert story in scoped
    assert feature not in scoped
    assert dev not in scoped

"""One-off: split workflow_templates.py into package."""
from __future__ import annotations

import pathlib

src_path = pathlib.Path("app/domain/workflow_templates.py")
lines = src_path.read_text(encoding="utf-8").splitlines(keepends=True)
base = pathlib.Path("app/domain/workflow_templates")
base.mkdir(exist_ok=True)


def chunk(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


(base / "_common.py").write_text(
    '"""Helpers compartidos para plantillas de workflow."""\n'
    + chunk(1, 86).replace(
        "EntityType = str  # feature | task | query | report | milestone\n\n", ""
    ),
    encoding="utf-8",
)

waterfall_body = chunk(88, 213) + chunk(452, 684) + chunk(740, 856)
(base / "waterfall.py").write_text(
    '"""Workflows waterfall (t1-t5)."""\n'
    "from __future__ import annotations\n\n"
    "import copy\n"
    "from typing import Any\n\n"
    "from app.domain.workflow_templates._common import *\n"
    "from app.domain.capabilities import (\n"
    "    FEATURE_TRANSITION_CANCELAR,\n"
    "    FEATURE_TRANSITION_COMPLETAR,\n"
    "    FEATURE_TRANSITION_COMPROMETER_SPRINT,\n"
    "    FEATURE_TRANSITION_CONFIRMAR,\n"
    "    FEATURE_TRANSITION_DEVOLVER_REWORK,\n"
    "    FEATURE_TRANSITION_ENVIAR_AL_PM,\n"
    "    FEATURE_TRANSITION_LIBERAR_CLIENTE,\n"
    "    FEATURE_TRANSITION_NO_FUNCIONA,\n"
    "    FEATURE_TRANSITION_PASAR_A_UAT,\n"
    "    FEATURE_TRANSITION_RECHAZAR_LIBERACION,\n"
    "    FEATURE_TRANSITION_VOLVER_BACKLOG,\n"
    "    KANBAN_TASK_CANCEL,\n"
    "    KANBAN_TASK_MOVE,\n"
    "    SCOPE_MILESTONE_CANCEL,\n"
    "    STORY_TRANSITION_COMPLETAR,\n"
    ")\n\n"
    + waterfall_body,
    encoding="utf-8",
)

scrum_body = chunk(215, 449) + chunk(687, 737)
(base / "scrum.py").write_text(
    '"""Workflows Scrum (t6-t7)."""\n'
    "from __future__ import annotations\n\n"
    "import copy\n"
    "from typing import Any\n\n"
    "from app.domain.workflow_templates._common import *\n"
    "from app.domain.workflow_templates.waterfall import default_feature_workflow_con_cliente\n"
    "from app.domain.capabilities import (\n"
    "    FEATURE_TRANSITION_CANCELAR,\n"
    "    FEATURE_TRANSITION_COMPLETAR,\n"
    "    FEATURE_TRANSITION_COMPROMETER_SPRINT,\n"
    "    FEATURE_TRANSITION_CONFIRMAR,\n"
    "    FEATURE_TRANSITION_DEVOLVER_REWORK,\n"
    "    FEATURE_TRANSITION_ENVIAR_AL_PM,\n"
    "    FEATURE_TRANSITION_LIBERAR_CLIENTE,\n"
    "    FEATURE_TRANSITION_NO_FUNCIONA,\n"
    "    FEATURE_TRANSITION_PASAR_A_UAT,\n"
    "    FEATURE_TRANSITION_RECHAZAR_LIBERACION,\n"
    "    FEATURE_TRANSITION_VOLVER_BACKLOG,\n"
    "    KANBAN_TASK_CANCEL,\n"
    "    KANBAN_TASK_MOVE,\n"
    "    SCOPE_SPRINT_CANCEL,\n"
    "    STORY_TRANSITION_CANCELAR,\n"
    "    STORY_TRANSITION_COMPLETAR,\n"
    "    STORY_TRANSITION_COMPROMETER_SPRINT,\n"
    "    STORY_TRANSITION_CONFIRMAR,\n"
    "    STORY_TRANSITION_DEVOLVER_REWORK,\n"
    "    STORY_TRANSITION_ENVIAR_AL_PM,\n"
    "    STORY_TRANSITION_LIBERAR_CLIENTE,\n"
    "    STORY_TRANSITION_NO_FUNCIONA,\n"
    "    STORY_TRANSITION_PASAR_A_UAT,\n"
    "    STORY_TRANSITION_RECHAZAR_LIBERACION,\n"
    "    STORY_TRANSITION_VOLVER_BACKLOG,\n"
    ")\n\n"
    + scrum_body,
    encoding="utf-8",
)

router_body = chunk(868, 915)
router_body = router_body.replace(
    "default_feature_workflow_scrum_interno()", "scrum.default_feature_workflow_scrum_interno()"
).replace(
    "default_feature_workflow_scrum_cliente()", "scrum.default_feature_workflow_scrum_cliente()"
).replace("default_sprint_workflow()", "scrum.default_sprint_workflow()").replace(
    "default_product_backlog_workflow()", "scrum.default_product_backlog_workflow()"
).replace(
    "default_task_workflow_scrum_dev()", "scrum.default_task_workflow_scrum_dev()"
).replace(
    "workflow_for_project_tipo(", "waterfall.workflow_for_project_tipo("
)
(base / "router.py").write_text(
    '"""Router de workflows por template/pack."""\n'
    "from __future__ import annotations\n\n"
    "from app.domain.project_templates import SCRUM_TEMPLATE_SLUGS\n"
    "from app.domain.workflow_templates import scrum, waterfall\n\n"
    + router_body,
    encoding="utf-8",
)

init = '''"""Plantillas de workflow por defecto (waterfall + scrum)."""
from app.domain.workflow_templates._common import *  # noqa: F403
from app.domain.workflow_templates.router import (
    workflow_for_project_tipo,
    workflow_for_template,
)
from app.domain.workflow_templates.scrum import (
    default_feature_workflow_scrum_base,
    default_feature_workflow_scrum_cliente,
    default_feature_workflow_scrum_interno,
    default_product_backlog_workflow,
    default_sprint_workflow,
    default_task_workflow_epic_container,
    default_task_workflow_scrum_dev,
    default_task_workflow_scrum_story_base,
    default_task_workflow_scrum_story_cliente,
    default_task_workflow_scrum_story_interno,
)
from app.domain.workflow_templates.waterfall import (
    default_feature_workflow_con_cliente,
    default_feature_workflow_freestyle,
    default_feature_workflow_interno,
    default_milestone_workflow,
    default_query_workflow,
    default_query_workflow_freestyle,
    default_report_workflow,
    default_report_workflow_freestyle,
    default_task_workflow,
)

__all__ = [
    "workflow_for_template",
    "workflow_for_project_tipo",
    "default_feature_workflow_con_cliente",
    "default_feature_workflow_interno",
    "default_feature_workflow_freestyle",
    "default_feature_workflow_scrum_base",
    "default_feature_workflow_scrum_interno",
    "default_feature_workflow_scrum_cliente",
    "default_task_workflow_scrum_story_base",
    "default_task_workflow_scrum_story_interno",
    "default_task_workflow_scrum_story_cliente",
    "default_task_workflow_epic_container",
    "default_task_workflow_scrum_dev",
    "default_task_workflow",
    "default_query_workflow",
    "default_query_workflow_freestyle",
    "default_report_workflow",
    "default_report_workflow_freestyle",
    "default_milestone_workflow",
    "default_sprint_workflow",
    "default_product_backlog_workflow",
]
'''
(base / "__init__.py").write_text(init, encoding="utf-8")
src_path.unlink()
print("done")

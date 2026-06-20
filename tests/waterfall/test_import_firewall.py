"""CI guard: capas genéricas no importan módulos del otro modo de delivery."""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _imports_in_file(rel_path: str) -> set[str]:
    path = REPO_ROOT / rel_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def test_generic_layers_do_not_import_scrum_modules() -> None:
    forbidden_prefixes = ("app.services.scrum", "app.services.scrum_")
    for rel in (
        "app/services/tasks.py",
        "app/services/features.py",
        "app/services/workflow/engine.py",
    ):
        mods = _imports_in_file(rel)
        for mod in mods:
            for prefix in forbidden_prefixes:
                assert not mod.startswith(prefix), f"{rel} imports {mod}"


def test_scrum_modules_do_not_import_waterfall_domain_services() -> None:
    forbidden = (
        "app.services.tasks",
        "app.services.features",
        "app.services.milestones",
    )
    for path in (REPO_ROOT / "app" / "services").glob("scrum*.py"):
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        mods = _imports_in_file(rel)
        for mod in mods:
            assert mod not in forbidden, f"{rel} imports {mod}"


def test_gates_generic_does_not_import_scrum_v2() -> None:
    mods = _imports_in_file("app/services/workflow/gates.py")
    for mod in mods:
        assert not mod.startswith("app.services.scrum"), (
            f"gates.py imports {mod}"
        )

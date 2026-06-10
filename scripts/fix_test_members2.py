"""Fix broken add_all(add_member_with_slug) patterns in tests."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tests"

# session.add_all([ add_member_with_slug(...), ... ])
BLOCK = re.compile(
    r"session\.add_all\(\s*\[\s*((?:add_member_with_slug\([^)]+\),?\s*)+)\s*\]\s*\)",
    re.MULTILINE,
)


def fix_add_all_block(match: re.Match) -> str:
    inner = match.group(1)
    calls = re.findall(r"add_member_with_slug\([^)]+\)", inner)
    return "\n".join(f"    {c}" for c in calls)


def fix_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    text = BLOCK.sub(lambda m: fix_add_all_block(m), text)
    text = text.replace(
        "add_member_with_slug(session, project,",
        "add_member_with_slug(db_session, project,",
    )
    text = text.replace(
        "add_member_with_slug(db_session, project,",
        "add_member_with_slug(session, project,",
    )
    # per-file: use db_session where fixture is db_session
    if "def " in text and "db_session" in text:
        text = text.replace(
            "add_member_with_slug(session, project,",
            "add_member_with_slug(db_session, project,",
        )
    if original != text:
        path.write_text(text, encoding="utf-8")
        print("fixed", path.name)


for p in ROOT.rglob("*.py"):
    fix_file(p)

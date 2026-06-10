"""One-off: replace ProjectMember(..., rol=) with add_member_with_slug."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tests"
PAT = re.compile(
    r"ProjectMember\(\s*project_id=([^,]+),\s*user_id=([^,]+),\s*rol=[\"']([^\"']+)[\"']\s*\)"
)


def ensure_import(text: str) -> str:
    if "add_member_with_slug" in text:
        return text
    marker = "from tests.org_helpers import"
    if marker in text:
        return text.replace(marker, f"{marker} add_member_with_slug,", 1)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            continue
        lines.insert(i, "from tests.org_helpers import add_member_with_slug")
        return "\n".join(lines)
    return "from tests.org_helpers import add_member_with_slug\n" + text


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not PAT.search(text):
        return False
    text = ensure_import(text)
    text = PAT.sub(
        r"add_member_with_slug(session, project, \2, '\3')",
        text,
    )
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    for path in ROOT.rglob("*.py"):
        if fix_file(path):
            print("fixed", path.relative_to(ROOT.parent))


if __name__ == "__main__":
    main()

from pathlib import Path

for path in Path("tests").rglob("*.py"):
    t = path.read_text(encoding="utf-8")
    n = t.replace("db_    add_member_with_slug", "add_member_with_slug")
    n = n.replace("session.add(add_member_with_slug(session,", "add_member_with_slug(session,")
    while "'))" in n and "add_member_with_slug(session" in n:
        n = n.replace("add_member_with_slug(session, project, pm_id, 'pm'))", "add_member_with_slug(session, project, pm_id, 'pm')")
        n = n.replace("add_member_with_slug(session, project, dev.id, 'dev'))", "add_member_with_slug(session, project, dev.id, 'dev')")
        n = n.replace("add_member_with_slug(session, project, qa.id, 'qa'))", "add_member_with_slug(session, project, qa.id, 'qa')")
        break
    if n != t:
        path.write_text(n, encoding="utf-8")
        print(path.name)

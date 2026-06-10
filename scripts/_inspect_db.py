import sqlite3

c = sqlite3.connect("data/v3.db")
print("version", c.execute("select version_num from alembic_version").fetchone())
print("members cols", [r[1] for r in c.execute("pragma table_info(project_members)")])
print("indexes", c.execute("select sql from sqlite_master where type='index' and tbl_name='project_members'").fetchall())
print("null role_id", c.execute("select count(*) from project_members where role_id is null").fetchone())

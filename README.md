# Proyecto Central — Backend v3

API **FastAPI** + **SQLAlchemy 2** + **Alembic**. Modelo **generic records + packs**: todas las entidades de proyecto viven en `project_records`.

Desarrollo local con **SQLite**; producción con **PostgreSQL** (`DATABASE_URL`).

Guía del stack: `[docs/CENTER_V3.md](../docs/CENTER_V3.md)` · Referencia técnica: `[docs/BACKEND_V3.md](../docs/BACKEND_V3.md)` · Modelo BD: `[docs/DBDIAGRAM.md](../docs/DBDIAGRAM.md)` · Alembic: `[docs/SQL_REFERENCE.md](../docs/SQL_REFERENCE.md)`.

## Requisitos

- Python 3.12+

## Instalación

```powershell
cd proyecto-central-backend-v3
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Arrancar

```powershell
uvicorn app.main:app --reload --port 8000
```


| URL                                                          | Uso          |
| ------------------------------------------------------------ | ------------ |
| [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) | Health check |
| [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)     | OpenAPI      |


## Autenticación


| Endpoint                                | Descripción              |
| --------------------------------------- | ------------------------ |
| `POST /api/v1/auth/register`            | Alta de usuario          |
| `POST /api/v1/auth/login`               | JWT (`sub`, `org_id`)    |
| `POST /api/v1/auth/switch-organization` | Cambiar org activa       |
| `GET /api/v1/auth/session`              | Usuario + orgs (Bearer)  |
| `GET /api/v1/auth/onboarding-status`    | ¿Necesita onboarding?    |
| `POST /api/v1/auth/forgot-password`     | Token reset (log en dev) |
| `POST /api/v1/auth/reset-password`      | Nueva contraseña         |


Todas las rutas de dominio exigen **JWT Bearer** (`Authorization: Bearer <token>`). El actor se deriva del claim `sub` (`get_current_actor_id` en `app/api/v1/auth_deps.py`). No se envía `actor_user_id` en body ni query.

Endpoints públicos sin JWT: `POST /auth/`*, `GET /health`, `GET /project-templates`, `POST /users` (registro), `GET /users/{id}`.

**API principal de dominio:**


| Superficie              | Prefijo                                       |
| ----------------------- | --------------------------------------------- |
| Records CRUD + workflow | `POST/PATCH/GET /projects/{id}/records`       |
| Access context + Studio | `GET /projects/{id}/access-context`           |
| Scrum (t6/t7)           | `/projects/{id}/scrum/`*                      |
| Portfolio PM            | `GET /projects/pm-portfolio?organization_id=` |


## Base de datos

Por defecto: `data/v3.db`. Migraciones al importar `app.main` o manual:

```powershell
alembic upgrade head
```

PostgreSQL en `.env`:

```
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/central_v3
```

Variables JWT (`.env`): `JWT_SECRET`, `JWT_EXPIRE_MINUTES` (ver defaults en `app/config.py`).

## Tests

```powershell
pytest -q
```

**216 tests** — fixtures JWT en `tests/conftest.py` (`auth_headers`).

## Datos demo

Un único script: reset de BD + seed vía API (JWT). **Requiere uvicorn en `:8000`.**

```powershell
.\.venv\Scripts\python.exe scripts/reset_and_seed_demo.py
```

Opciones: `--reset-only`, `--seed-only`.

Cuentas: `pm@center.demo`, `dev@center.demo`, `dev2@center.demo`, `qa@center.demo`, `cliente@center.demo` / `demo12345`.

Org: **Center Demo**. Cuatro proyectos (plantillas canónicas):


| Proyecto                  | Template           | Notas                                                         |
| ------------------------- | ------------------ | ------------------------------------------------------------- |
| Portal Cliente Demo       | t1_cliente_clasico | Waterfall con cliente: hitos, features, kanban, hub, reportes |
| Plataforma Interna Center | t3_interno_clasico | Waterfall interno: UAT, consultas, hub                        |
| Logistics Hub             | t6_scrum_interno   | Scrum interno: 4 sprints, backlog, ceremonias                 |
| E-commerce Relaunch       | t7_scrum_cliente   | Scrum con cliente: validación UAT externa                     |


Si `v3.db` está bloqueado por uvicorn, el script vacía tablas sin detener el servidor. Si borra el fichero, reiniciá uvicorn antes de `--seed-only`.

## Estructura

```
app/
  main.py
  api/v1/
    router.py              # Agregador /api/v1
    auth.py, auth_deps.py   # JWT
    organizations.py, users.py
    projects.py             # CRUD, members, portfolio, team-board
    project_access.py       # access-context (get_access_context), studio, comm rules
    project_customization.py
    project_records.py      # Records CRUD, transition, inbox
    scrum.py                # Métricas y ceremonias (t6/t7)
    hub_entries.py          # anidado bajo projects
    comments.py, attachments.py
    audit_logs.py, timeline.py  # anidados bajo projects
  domain/                   # packs, capabilities, templates, project_mode
  services/
    records/generic_store.py
    delivery/               # WaterfallRecordService / ScrumRecordService
    workflow/engine.py
    packs.py, access.py     # access.py: guards; access-context en project_access.py
  models/entities.py
  schemas/
scripts/
  reset_and_seed_demo.py    # único script: reset BD + seed (t1, t3, t6, t7)
alembic/versions/           # head: d3e4f5a6b7c8 (ver docs/SQL_REFERENCE.md)
tests/
  conftest.py               # auth_headers, db_session, api_client
```


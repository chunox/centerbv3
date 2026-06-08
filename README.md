# Proyecto Central — Backend v3

API **FastAPI** + **SQLAlchemy 2** + **Alembic**. Desarrollo local con **SQLite**; producción con **PostgreSQL** (`DATABASE_URL`).

Guía del stack: [`docs/CENTER_V3.md`](../docs/CENTER_V3.md) · Referencia técnica: [`docs/BACKEND_V3.md`](../docs/BACKEND_V3.md).

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

| URL | Uso |
| --- | --- |
| http://127.0.0.1:8000/health | Health check |
| http://127.0.0.1:8000/docs | OpenAPI |

## Autenticación

| Endpoint | Descripción |
| -------- | ----------- |
| `POST /api/v1/auth/register` | Alta de usuario |
| `POST /api/v1/auth/login` | JWT (`sub`, `org_id`) |
| `POST /api/v1/auth/switch-organization` | Cambiar org activa |
| `GET /api/v1/auth/me` | Usuario + orgs (Bearer) |
| `GET /api/v1/auth/onboarding-status` | ¿Necesita onboarding? |

Las mutaciones de dominio siguen usando `actor_user_id` en body; el listado de proyectos acepta JWT sin `user_id` en query.

## Hitos — orden

- **Crear:** el servidor asigna `orden = count + 1` (ignora el body).
- **Eliminar:** recompacta hitos a `1..N` (`compact_milestone_ordenes`).
- **PATCH `orden`:** reinserta y renumerar (`reorder_milestone`).

Tests: `tests/test_milestone_order.py`.

## Base de datos

Por defecto: `data/v3.db`. Migraciones al importar `app.main` o manual:

```powershell
alembic upgrade head
```

PostgreSQL en `.env`:

```
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/central_v3
```

## Tests

```powershell
pytest -q
```

70 tests (suite completa). Smoke en vivo: `scripts/qa_live_smoke.py`.

## Estructura

```
app/
  main.py
  api/v1/
    auth.py, auth_deps.py
    organizations.py
    projects.py, milestones.py, …
  services/
    milestones.py    # sync estado, orden, cancel cascada
    organizations.py
    auth_tokens.py
  models/entities.py
alembic/versions/
tests/
```

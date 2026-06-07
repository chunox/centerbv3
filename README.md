# Proyecto Central — Backend v3

API con **FastAPI**, **SQLAlchemy 2** y **Alembic**. Desarrollo local con **SQLite**; producción con **PostgreSQL** cambiando solo `DATABASE_URL`.

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

## Arrancar el servidor

```powershell
uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Base de datos

Por defecto usa `data/v3.db` (SQLite). Las migraciones se aplican al importar `app.main`.

### Migraciones manuales

```powershell
alembic upgrade head
alembic revision -m "descripcion" --autogenerate
```

### PostgreSQL

En `.env`:

```
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/central_v3
```

Crear la base en Postgres y ejecutar `alembic upgrade head`.

## Tests

```powershell
pytest
```

## Estructura

```
app/
  main.py              # FastAPI + CORS
  config.py            # Settings (.env)
  database.py          # Engine, Session, Base
  database_migrations.py
  models/entities.py   # Modelos SQLAlchemy
  schemas/             # Pydantic
  api/v1/              # Routers
alembic/versions/      # Migraciones
data/                  # SQLite (gitignored)
```

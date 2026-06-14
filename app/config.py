"""
Configuración vía variables de entorno (.env).

demo_mode=True permite ?user_id= en algunos endpoints sin Bearer (desarrollo).
jwt_* define el token usado por el frontend demo.
"""
from pathlib import Path
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = (ROOT / "data" / "v3.db").resolve()
_DEFAULT_UPLOADS = (ROOT / "data" / "uploads").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{_DEFAULT_DB.as_posix()}"
    cors_origins: str = "*"

    milestone_sync_enabled: bool = False
    milestone_sync_actor_user_id: UUID | None = None
    milestone_sync_hour: int = 2
    milestone_sync_minute: int = 0

    uploads_dir: str = _DEFAULT_UPLOADS.as_posix()
    upload_max_bytes: int = 25 * 1024 * 1024

    demo_mode: bool = True
    communication_rules_only: bool = True
    jwt_secret: str = "center-v3-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    @property
    def uploads_path(self) -> Path:
        path = Path(self.uploads_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()

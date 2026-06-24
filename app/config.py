from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de datos
    # psycopg v3: usar postgresql+psycopg://
    database_url: str = "sqlite:///./center_mvp1.db"

    # JWT
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_USE_64_BYTES_HEX"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Archivos adjuntos
    upload_dir: str = "data/uploads"
    upload_max_mb: int = 50

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    # Entorno
    environment: str = "development"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()

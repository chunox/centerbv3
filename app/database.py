"""Engine SQLAlchemy + sesión. SQLite con foreign_keys=ON en cada conexión."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args: dict = {}
if settings.is_sqlite:
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _sqlite_foreign_keys(dbapi_conn, _connection_record) -> None:
    if settings.is_sqlite:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

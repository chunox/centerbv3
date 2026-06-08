import hashlib

try:
    import bcrypt
except ImportError:  # pragma: no cover
    bcrypt = None  # type: ignore[assignment]

_BCRYPT_PREFIX = "$2b$"


def hash_password(plain: str) -> str:
    """Hash seguro para nuevas contraseñas (bcrypt)."""
    if bcrypt is None:
        return hashlib.sha256(plain.encode("utf-8")).hexdigest()
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    if password_hash.startswith(_BCRYPT_PREFIX) and bcrypt is not None:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    return hash_password_legacy(plain) == password_hash


def hash_password_legacy(plain: str) -> str:
    """SHA-256 legacy (demo / migración lazy al login)."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def needs_rehash(password_hash: str) -> bool:
    return not password_hash.startswith(_BCRYPT_PREFIX)

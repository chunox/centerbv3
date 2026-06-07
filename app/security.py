import hashlib


def hash_password(plain: str) -> str:
    """Hash simple para aprender; en producción usa bcrypt/argon2."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()

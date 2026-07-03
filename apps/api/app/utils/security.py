"""Password hashing (bcrypt), admin JWTs (HS256) and Fernet secret encryption.

Auth paths favour explicitness over cleverness — every function here is
short and does exactly one thing.
"""
import datetime as dt

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.config import get_settings

JWT_ALGORITHM = "HS256"


# --- Passwords -------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed stored hash — treat as auth failure, never as a crash.
        return False


# --- JWT ---------------------------------------------------------------------

def _create_token(subject: int | str, token_type: str, ttl: dt.timedelta, extra: dict | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict = {"sub": str(subject), "type": token_type, "iat": now, "exp": now + ttl}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, get_settings().JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(admin_id: int, role: str) -> str:
    ttl = dt.timedelta(minutes=get_settings().JWT_ACCESS_TTL_MINUTES)
    return _create_token(admin_id, "access", ttl, {"role": role})


def create_refresh_token(admin_id: int) -> str:
    ttl = dt.timedelta(days=get_settings().JWT_REFRESH_TTL_DAYS)
    return _create_token(admin_id, "refresh", ttl)


def decode_token(token: str) -> dict:
    """Decode + verify signature/expiry. Raises jwt.PyJWTError on any problem."""
    return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[JWT_ALGORITHM])


# --- Fernet (provider API keys at rest) ---------------------------------------

def _fernet() -> Fernet:
    key = get_settings().ENCRYPTION_KEY
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured — cannot handle provider secrets")
    return Fernet(key.encode("utf-8"))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")

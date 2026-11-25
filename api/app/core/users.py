"""Local users in one JSON file (MONICOMM_USERS_FILE). Passwords are kept only as scrypt hashes.

Needs no internet, so it also works on the closed network. One api process writes the file.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import Settings

Role = Literal["admin", "technician", "viewer"]
NAME = re.compile(r"[a-z0-9][a-z0-9._@+-]{0,63}")  # a plain name or an email address
MIN_PASSWORD = 8
MAX_PASSWORD = 200
MAX_USERS = 200
SCRYPT = {"n": 2**14, "r": 8, "p": 5, "maxmem": 64 * 1024 * 1024}

_write_lock = threading.Lock()
_hash_slots = threading.BoundedSemaphore(4)  # each hash takes about 16 MB


class UsersError(RuntimeError):
    """code: damaged, exists, not_found, last_admin, too_many, save_failed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class StoredUser(BaseModel):
    name: str
    role: Role
    password_hash: str


class UsersFile(BaseModel):
    users: list[StoredUser] = []


class NewPassword(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD)


class NewUser(NewPassword):
    name: str
    role: Role

    @field_validator("name")
    @classmethod
    def normalized(cls, value: str) -> str:
        name = normalize(value)
        if not NAME.fullmatch(name):
            raise ValueError("invalid name")
        return name


def normalize(name: str) -> str:
    return name.strip().lower()


def _derive(password: str, salt: bytes) -> bytes:
    with _hash_slots:
        return hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    parts = (salt, _derive(password, salt))
    return "scrypt$" + "$".join(base64.b64encode(p).decode() for p in parts)


def _matches(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        return hmac.compare_digest(
            _derive(password, base64.b64decode(salt)), base64.b64decode(digest)
        )
    except ValueError:
        return False


# Checked when the name is unknown, so both cases take the same time.
_NOBODY = hash_password(secrets.token_hex(16))


def load(settings: Settings) -> list[StoredUser]:
    try:
        text = Path(settings.users_file).read_text("utf-8")
        return UsersFile.model_validate_json(text).users
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError, ValidationError) as e:
        raise UsersError("damaged") from e


def find(settings: Settings, name: str) -> StoredUser | None:
    """None also when the file is damaged: nobody gets in, and nothing overwrites it."""
    try:
        return next((u for u in load(settings) if u.name == name), None)
    except UsersError:
        return None


def verify(settings: Settings, name: str, password: str) -> StoredUser | None:
    user = find(settings, normalize(name))
    ok = _matches(password, user.password_hash if user else _NOBODY)
    return user if ok else None


def _save(settings: Settings, users: list[StoredUser]) -> None:
    path = Path(settings.users_file)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(UsersFile(users=users).model_dump_json(indent=2))
        os.replace(tmp, path)  # a reader never sees half a file
    except OSError as e:
        raise UsersError("save_failed") from e


def add(settings: Settings, new: NewUser) -> None:
    stored = StoredUser(name=new.name, role=new.role, password_hash=hash_password(new.password))
    with _write_lock:
        users = load(settings)
        if any(u.name == new.name for u in users):
            raise UsersError("exists")
        if len(users) >= MAX_USERS:
            raise UsersError("too_many")
        _save(settings, [*users, stored])


def remove(settings: Settings, name: str) -> None:
    with _write_lock:
        users = load(settings)
        rest = [u for u in users if u.name != name]
        if len(rest) == len(users):
            raise UsersError("not_found")
        if not any(u.role == "admin" for u in rest):
            raise UsersError("last_admin")
        _save(settings, rest)


def set_password(settings: Settings, name: str, new: NewPassword) -> None:
    password_hash = hash_password(new.password)
    with _write_lock:
        users = load(settings)
        if not any(u.name == name for u in users):
            raise UsersError("not_found")
        changed = [
            u.model_copy(update={"password_hash": password_hash}) if u.name == name else u
            for u in users
        ]
        _save(settings, changed)

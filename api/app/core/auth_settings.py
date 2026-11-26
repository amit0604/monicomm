"""LDAP and SSO settings: the .env values, plus what an admin saved on the Admin page.

The saved file (MONICOMM_AUTH_SETTINGS_FILE, on the auth-data volume, mode 600) holds a whole
section; a section that isn't saved comes from .env. A saved empty secret keeps the .env one.
Secrets are never returned by the API (see modules/admin/auth_methods.py).
"""

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings

DefaultRole = Literal["viewer", "technician", "none"]
Section = Literal["ldap", "sso"]
SECRET = {"ldap": "bind_password", "sso": "client_secret"}

_lock = threading.Lock()


class LdapSettings(BaseModel):
    url: str = ""
    start_tls: bool = False
    ca_file: str = ""
    bind_dn: str = ""
    bind_password: str = ""
    base_dn: str = ""
    user_filter: str = "(|(sAMAccountName={username})(uid={username}))"
    admin_group: str = ""
    technician_group: str = ""
    default_role: DefaultRole = "viewer"

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.base_dn)


class SsoSettings(BaseModel):
    issuer: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: str = "openid profile email"
    groups_claim: str = "groups"
    admin_group: str = ""
    technician_group: str = ""
    default_role: DefaultRole = "viewer"
    label: str = "SSO"
    redirect_url: str = ""
    ca_file: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.client_id)


MODELS: dict[str, type[LdapSettings] | type[SsoSettings]] = {
    "ldap": LdapSettings,
    "sso": SsoSettings,
}


def from_env(section: Section, settings: Settings | None = None) -> LdapSettings | SsoSettings:
    settings = settings or get_settings()
    model = MODELS[section]
    values = {f: getattr(settings, f"{section}_{f}") for f in model.model_fields}
    if values.get("default_role") not in ("viewer", "technician", "none"):
        values["default_role"] = "viewer"
    return model(**values)


def _read(settings: Settings) -> dict:
    try:
        data = json.loads(Path(settings.auth_settings_file).read_text("utf-8"))
    except (OSError, ValueError):
        return {}  # missing or damaged: .env applies
    return data if isinstance(data, dict) else {}


def saved(section: Section, settings: Settings | None = None) -> LdapSettings | SsoSettings | None:
    settings = settings or get_settings()
    raw = _read(settings).get(section)
    if not isinstance(raw, dict):
        return None
    try:
        return MODELS[section].model_validate(raw)
    except ValidationError:
        return None


def merge(
    section: Section, env: LdapSettings | SsoSettings, stored: LdapSettings | SsoSettings | None
) -> LdapSettings | SsoSettings:
    if stored is None:
        return env
    secret = SECRET[section]
    if not getattr(stored, secret):
        stored = stored.model_copy(update={secret: getattr(env, secret)})
    return stored


def current(section: Section) -> LdapSettings | SsoSettings:
    settings = get_settings()
    return merge(section, from_env(section, settings), saved(section, settings))


def secret_source(section: Section) -> Literal["none", "env", "saved"]:
    stored = saved(section)
    if stored is not None and getattr(stored, SECRET[section]):
        return "saved"
    return "env" if getattr(from_env(section), SECRET[section]) else "none"


def _write(settings: Settings, data: dict) -> None:
    path = Path(settings.auth_settings_file)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)  # a reader never sees half a file


def save(section: Section, values: LdapSettings | SsoSettings) -> None:
    settings = get_settings()
    with _lock:
        data = _read(settings)
        data[section] = values.model_dump()
        _write(settings, data)


def reset(section: Section) -> None:
    settings = get_settings()
    with _lock:
        data = _read(settings)
        if data.pop(section, None) is not None:
            _write(settings, data)


def role_for(
    groups: list[str], admin_group: str, technician_group: str, default_role: DefaultRole
) -> Literal["admin", "technician", "viewer"] | None:
    """Admin group first, then technician, then the default. None = not allowed in."""
    have = {g.strip().lower() for g in groups}
    if admin_group and admin_group.strip().lower() in have:
        return "admin"
    if technician_group and technician_group.strip().lower() in have:
        return "technician"
    return None if default_role == "none" else default_role

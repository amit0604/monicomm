"""Admin page API for the login methods: /api/v1/admin/auth/{ldap,sso}. Signed-in admins only.

Save, delete and test LDAP and SSO settings. Secrets (the LDAP bind password, the SSO client
secret) are write-only: no reply ever contains them. Testing never saves anything.
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.core import auth_settings, ldap_auth, sso
from app.core.airgap import check_url
from app.modules.admin.router import AdminDep

log = logging.getLogger(__name__)
DN = Field(default="", max_length=500)


def _secret(value: SecretStr | None) -> SecretStr | None:
    if value is not None and not 0 < len(value.get_secret_value()) <= 500:
        raise ValueError("invalid secret")
    return value


class LdapForm(BaseModel):
    url: str = Field(min_length=1, max_length=300)
    start_tls: bool = False
    ca_file: str = Field(default="", max_length=300)
    bind_dn: str = DN
    bind_password: SecretStr | None = None  # None = keep the current one
    base_dn: str = Field(min_length=1, max_length=500)
    user_filter: str = Field(min_length=3, max_length=500)
    admin_group: str = DN
    technician_group: str = DN
    default_role: auth_settings.DefaultRole = "viewer"
    username: str = Field(default="", max_length=128)  # test only: a user to look up

    _check_secret = field_validator("bind_password")(_secret)

    @field_validator("user_filter")
    @classmethod
    def has_placeholder(cls, value: str) -> str:
        if "{username}" not in value or not value.startswith("("):
            raise ValueError("the filter needs {username}")
        return value


class SsoForm(BaseModel):
    issuer: str = Field(min_length=1, max_length=300)
    client_id: str = Field(min_length=1, max_length=200)
    client_secret: SecretStr | None = None
    scopes: str = Field(default="openid profile email", max_length=200)
    groups_claim: str = Field(default="groups", max_length=100)
    admin_group: str = DN
    technician_group: str = DN
    default_role: auth_settings.DefaultRole = "viewer"
    label: str = Field(default="SSO", min_length=1, max_length=40)
    redirect_url: str = Field(default="", max_length=300)
    ca_file: str = Field(default="", max_length=300)

    _check_secret = field_validator("client_secret")(_secret)

    @field_validator("scopes")
    @classmethod
    def has_openid(cls, value: str) -> str:
        if "openid" not in value.split():
            raise ValueError("scopes need openid")
        return value


class TestResult(BaseModel):
    ok: bool
    error: str | None = None
    user: dict | None = None  # LDAP: the test user's DN and role


def _ldap_from(form: LdapForm) -> auth_settings.LdapSettings:
    try:
        check_url(form.url.strip(), {"ldap", "ldaps"}, "LDAP")
    except ValueError:
        raise HTTPException(400, "external_url") from None
    stored = auth_settings.saved("ldap")
    secret = form.bind_password.get_secret_value() if form.bind_password else ""
    return auth_settings.LdapSettings(
        **form.model_dump(exclude={"bind_password", "username"}),
        bind_password=secret or (stored.bind_password if stored else ""),
    )


def _sso_from(form: SsoForm) -> auth_settings.SsoSettings:
    try:
        sso._url(form.issuer.strip().rstrip("/"))
        if form.redirect_url:
            check_url(form.redirect_url, {"http", "https"}, "SSO redirect")
    except (sso.SsoError, ValueError):
        raise HTTPException(400, "external_url") from None
    stored = auth_settings.saved("sso")
    secret = form.client_secret.get_secret_value() if form.client_secret else ""
    return auth_settings.SsoSettings(
        **form.model_dump(exclude={"client_secret"}),
        client_secret=secret or (stored.client_secret if stored else ""),
    )


def _view(section: auth_settings.Section, request: Request) -> dict:
    now = auth_settings.current(section)
    view = now.model_dump(exclude={auth_settings.SECRET[section]})
    view |= {
        "enabled": now.enabled,
        "secret_source": auth_settings.secret_source(section),
        "saved": auth_settings.saved(section) is not None,
    }
    if section == "sso":  # what to register at the identity provider
        view["callback_url"] = now.redirect_url or str(request.url_for("sso_callback"))
    return view


def _save(
    section: auth_settings.Section,
    values: auth_settings.LdapSettings | auth_settings.SsoSettings,
    admin_name: str,
) -> None:
    try:
        auth_settings.save(section, values)
    except OSError as e:
        log.error("admin: can't save the %s settings: %s", section, type(e).__name__)
        raise HTTPException(500, "save_failed") from None
    log.info("admin: %s saved the %s login settings", admin_name, section)


router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin"])
Name = Literal["ldap", "sso"]


@router.get("/{section}")
def read(section: Name, request: Request, _admin: AdminDep) -> dict:
    return _view(section, request)


@router.delete("/{section}")
def reset(section: Name, request: Request, admin: AdminDep) -> dict:
    auth_settings.reset(section)
    log.info("admin: %s reset the %s login settings to .env", admin.name, section)
    return _view(section, request)


@router.put("/ldap")
def save_ldap(form: LdapForm, request: Request, admin: AdminDep) -> dict:
    _save("ldap", _ldap_from(form), admin.name)
    return _view("ldap", request)


@router.put("/sso")
def save_sso(form: SsoForm, request: Request, admin: AdminDep) -> dict:
    _save("sso", _sso_from(form), admin.name)
    return _view("sso", request)


# Not async: the LDAP and HTTP calls block, so they run in the thread pool.
@router.post("/ldap/test")
def test_ldap(form: LdapForm, _admin: AdminDep) -> TestResult:
    """Connect, bind as the service account and read the base DN; optionally look up a user."""
    return TestResult(**ldap_auth.test_connection(_ldap_from(form), form.username))


@router.post("/sso/test")
def test_sso(form: SsoForm, _admin: AdminDep) -> TestResult:
    """Read the identity provider's discovery document and signing keys."""
    return TestResult(**sso.test_connection(_sso_from(form)))

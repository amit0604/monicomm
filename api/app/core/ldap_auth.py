"""LDAP / Active Directory login. Read-only: search and bind, never a write (CLAUDE.md rule 3).

1. Bind as the service account (or anonymously) and find exactly one entry for the user name.
2. Bind as that entry with the password the user typed. An empty password is refused first:
   LDAP treats it as an anonymous bind, which would "succeed".
3. The role comes from memberOf (admin group, technician group, else the default role).
   Nested groups are not followed.
"""

import ssl
from dataclasses import dataclass

from ldap3 import BASE, NONE, SUBTREE, SYNC, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException, LDAPSocketOpenError, LDAPStartTLSError
from ldap3.utils.conv import escape_filter_chars

from app.core.airgap import check_url
from app.core.auth_settings import LdapSettings, role_for

TIMEOUT_S = 10
ATTRIBUTES = ["displayName", "cn", "mail", "memberOf"]
_STRATEGY = SYNC  # tests use ldap3's MOCK_SYNC


class LdapError(RuntimeError):
    """code: external_url, unreachable, tls_failed, bind_failed, base_not_found, failed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class NotAllowed(RuntimeError):
    """The password is right, but no group gives this user a role (default role "none")."""


@dataclass
class DirectoryUser:
    name: str
    display_name: str | None
    email: str | None
    role: str


def _make_server(cfg: LdapSettings) -> Server:
    try:
        check_url(cfg.url, {"ldap", "ldaps"}, "LDAP")
    except ValueError:
        raise LdapError("external_url") from None
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=cfg.ca_file or None)
    return Server(
        cfg.url,
        use_ssl=cfg.url.startswith("ldaps://"),
        tls=tls,
        connect_timeout=TIMEOUT_S,
        get_info=NONE,
    )


def _bind(cfg: LdapSettings, server: Server, dn: str | None, password: str | None) -> Connection:
    """An open, bound connection; LdapError when it can't connect or the bind is refused."""
    conn = Connection(
        server,
        user=dn,
        password=password,
        client_strategy=_STRATEGY,
        receive_timeout=TIMEOUT_S,
        read_only=True,
        raise_exceptions=False,
    )
    try:
        conn.open()
        if cfg.start_tls and _STRATEGY == SYNC:
            conn.start_tls()
        if not conn.bind():
            conn.unbind()
            raise LdapError("bind_failed")
    except LDAPStartTLSError:
        raise LdapError("tls_failed") from None
    except LDAPSocketOpenError as e:
        cause = e.__context__
        raise LdapError(
            "tls_failed" if isinstance(cause, ssl.SSLError) else "unreachable"
        ) from None
    except LDAPException:
        raise LdapError("unreachable") from None
    return conn


def _first(entry: dict, name: str) -> str | None:
    value = entry.get(name)
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def _find(cfg: LdapSettings, server: Server, username: str) -> tuple[str, dict] | None:
    service = _bind(cfg, server, cfg.bind_dn or None, cfg.bind_password or None)
    try:
        query = cfg.user_filter.replace("{username}", escape_filter_chars(username))
        ok = service.search(cfg.base_dn, query, SUBTREE, attributes=ATTRIBUTES, size_limit=2)
        if not ok and service.result.get("description") == "noSuchObject":
            raise LdapError("base_not_found")
        hits = [r for r in service.response or [] if r.get("type") == "searchResEntry"]
        if len(hits) != 1:  # none, or ambiguous: never guess which person this is
            return None
        return hits[0]["dn"], dict(hits[0].get("attributes") or {})
    finally:
        service.unbind()


def authenticate(cfg: LdapSettings, username: str, password: str) -> DirectoryUser | None:
    """The user, None for a wrong name or password, NotAllowed, or LdapError (server problem)."""
    username = username.strip()
    if not username or not password:
        return None
    server = _make_server(cfg)
    found = _find(cfg, server, username)
    if found is None:
        return None
    dn, attrs = found
    try:
        _bind(cfg, server, dn, password).unbind()
    except LdapError as e:
        if e.code == "bind_failed":
            return None
        raise
    groups = attrs.get("memberOf") or []
    role = role_for(
        groups if isinstance(groups, list) else [groups],
        cfg.admin_group,
        cfg.technician_group,
        cfg.default_role,
    )
    if role is None:
        raise NotAllowed(username)
    return DirectoryUser(
        name=username.lower(),
        display_name=_first(attrs, "displayName") or _first(attrs, "cn"),
        email=_first(attrs, "mail"),
        role=role,
    )


def test_connection(cfg: LdapSettings, username: str = "") -> dict:
    """Service bind + read the base DN; with a user name, also look that user up (no password)."""
    if not cfg.url or not cfg.base_dn:
        return {"ok": False, "error": "incomplete"}
    try:
        server = _make_server(cfg)
        service = _bind(cfg, server, cfg.bind_dn or None, cfg.bind_password or None)
        try:
            if not service.search(cfg.base_dn, "(objectClass=*)", BASE, attributes=[]):
                return {"ok": False, "error": "base_not_found"}
        finally:
            service.unbind()
        if not username.strip():
            return {"ok": True}
        found = _find(cfg, server, username.strip())
    except LdapError as e:
        return {"ok": False, "error": e.code}
    if found is None:
        return {"ok": False, "error": "user_not_found"}
    groups = found[1].get("memberOf") or []
    role = role_for(
        groups if isinstance(groups, list) else [groups],
        cfg.admin_group,
        cfg.technician_group,
        cfg.default_role,
    )
    return {"ok": True, "user": {"dn": found[0], "role": role or "none"}}

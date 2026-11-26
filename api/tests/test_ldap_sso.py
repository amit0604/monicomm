"""LDAP and SSO login, and the Admin page API that sets them up (with Test connection)."""

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from ldap3 import MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server

from app.core import auth, ldap_auth, sso, users
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct-horse-1"
BASE = "dc=corp,dc=example"
SERVICE = f"cn=svc-monicomm,ou=service,{BASE}"
ADMINS = f"cn=monicomm-admins,ou=groups,{BASE}"
TECHS = f"cn=monicomm-techs,ou=groups,{BASE}"
ISSUER = "https://idp.corp.example/realms/it"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setitem(users.SCRYPT, "n", 16)  # fast hashes
    for key, value in {
        "ENV": "prod",
        "AUTH_PROVIDER": "local",
        "USERS_FILE": str(tmp_path / "users.json"),
        "AUTH_SETTINGS_FILE": str(tmp_path / "auth-settings.json"),
        "INTERNAL_DOMAINS": "corp.example",
        "LDAP_URL": "ldap://dc01.corp.example",
        "LDAP_BASE_DN": BASE,
        "LDAP_BIND_DN": SERVICE,
        "LDAP_BIND_PASSWORD": "svc-secret",
        "LDAP_ADMIN_GROUP": ADMINS,
        "LDAP_TECHNICIAN_GROUP": TECHS,
        "LDAP_DEFAULT_ROLE": "none",
    }.items():
        monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    auth._sessions.clear()
    auth._failures.clear()
    users.add(get_settings(), users.NewUser(name="admin", role="admin", password=PASSWORD))
    yield TestClient(app)
    auth._sessions.clear()
    auth._failures.clear()
    sso._pending.clear()
    get_settings.cache_clear()


@pytest.fixture
def directory(monkeypatch):
    """An in-memory directory (ldap3 MOCK_SYNC); entries are shared through the Server."""
    server = Server("dc01", get_info=OFFLINE_AD_2012_R2)
    seed = Connection(server, client_strategy=MOCK_SYNC)
    people = f"ou=people,{BASE}"

    def person(uid, password, groups, **extra):
        seed.strategy.add_entry(
            f"cn={uid},{people}",
            {
                "objectClass": ["person"],
                "sAMAccountName": uid,
                "userPassword": password,
                "memberOf": groups,
                **extra,
            },
        )

    seed.strategy.add_entry(BASE, {"objectClass": ["domain"]})
    seed.strategy.add_entry(SERVICE, {"objectClass": ["person"], "userPassword": "svc-secret"})
    person("alice", "alice-pw", [ADMINS], displayName="Alice Levi", mail="alice@corp.example")
    person("bob", "bob-pw", [TECHS])
    person("carol", "carol-pw", [])
    person("admin", "ldap-admin-pw", [ADMINS])  # same name as the local admin
    monkeypatch.setattr(ldap_auth, "_STRATEGY", MOCK_SYNC)
    monkeypatch.setattr(ldap_auth, "_make_server", lambda cfg: server)
    return server


def login(client, name, password):
    return client.post("/api/v1/auth/session", json={"name": name, "password": password})


def admin(client):
    assert login(client, "admin", PASSWORD).status_code == 200
    return client


# LDAP sign in


def test_ldap_user_signs_in_with_the_role_of_their_group(client, directory):
    res = login(client, "Alice", "alice-pw")
    assert res.status_code == 200
    assert res.json() == {
        "name": "alice",
        "role": "admin",
        "display_name": "Alice Levi",
        "email": "alice@corp.example",
        "source": "ldap",
    }
    assert client.get("/api/v1/auth/me").json()["source"] == "ldap"
    assert client.get("/api/v1/modules").status_code == 200
    assert login(client, "bob", "bob-pw").json()["role"] == "technician"


def test_ldap_refuses_wrong_passwords_injection_and_users_without_a_group(client, directory):
    assert login(client, "alice", "wrong").status_code == 401
    assert login(client, "nobody", "x").status_code == 401
    assert login(client, "*", "alice-pw").status_code == 401  # filter characters are escaped
    assert login(client, "carol", "carol-pw").json()["detail"] == "not_allowed"


def test_a_local_account_wins_over_the_directory(client, directory):
    assert login(client, "admin", "ldap-admin-pw").status_code == 401
    assert login(client, "admin", PASSWORD).json()["source"] == "local"


def test_ldap_down_is_503_and_local_admins_still_get_in(client, monkeypatch):
    def down(cfg):
        raise ldap_auth.LdapError("unreachable")

    monkeypatch.setattr(ldap_auth, "_make_server", down)
    assert login(client, "alice", "alice-pw").json()["detail"] == "directory_unavailable"
    assert login(client, "admin", PASSWORD).status_code == 200


def test_empty_password_is_never_sent_to_the_directory(client, directory):
    cfg = ldap_auth.LdapSettings(url="ldap://dc01", base_dn=BASE)
    assert ldap_auth.authenticate(cfg, "alice", "") is None


def test_login_page_methods(client):
    assert client.get("/api/v1/auth/methods").json() == {"local": True, "ldap": True, "sso": None}


# Admin page: LDAP settings and Test connection

LDAP_FORM = {
    "url": "ldap://dc01.corp.example",
    "bind_dn": SERVICE,
    "bind_password": "svc-secret",
    "base_dn": BASE,
    "user_filter": "(sAMAccountName={username})",
    "admin_group": ADMINS,
    "technician_group": TECHS,
    "default_role": "viewer",
}


def test_ldap_test_connection(client, directory):
    admin(client)
    url = "/api/v1/admin/auth/ldap/test"
    assert client.post(url, json=LDAP_FORM).json() == {"ok": True, "error": None, "user": None}
    found = client.post(url, json=LDAP_FORM | {"username": "bob"}).json()
    assert found["user"] == {"dn": f"cn=bob,ou=people,{BASE}", "role": "technician"}
    assert (
        client.post(url, json=LDAP_FORM | {"username": "zed"}).json()["error"] == "user_not_found"
    )
    wrong = client.post(url, json=LDAP_FORM | {"bind_password": "nope"}).json()
    assert wrong == {"ok": False, "error": "bind_failed", "user": None}


def test_ldap_settings_are_saved_without_ever_returning_the_secret(client, directory):
    admin(client)
    url = "/api/v1/admin/auth/ldap"
    view = client.get(url).json()
    assert view["secret_source"] == "env" and not view["saved"] and "bind_password" not in view
    saved = client.put(url, json=LDAP_FORM | {"bind_password": "new-secret"}).json()
    assert saved["saved"] and saved["secret_source"] == "saved" and "new-secret" not in str(saved)
    kept = client.put(url, json=LDAP_FORM | {"bind_password": None}).json()  # keep the secret
    assert kept["secret_source"] == "saved"
    stored = json.loads(Path(get_settings().auth_settings_file).read_text("utf-8"))
    assert stored["ldap"]["bind_password"] == "new-secret"
    assert client.delete(url).json()["saved"] is False


def test_admin_login_settings_are_checked_and_admin_only(client, directory):
    assert client.get("/api/v1/admin/auth/ldap").status_code == 401
    login(client, "bob", "bob-pw")
    assert client.get("/api/v1/admin/auth/ldap").status_code == 403
    admin(client)
    url = "/api/v1/admin/auth/ldap"
    public = client.put(url, json=LDAP_FORM | {"url": "ldap://ldap.example.com"})
    assert public.json()["detail"] == "external_url"  # outside the closed network
    assert client.put(url, json=LDAP_FORM | {"user_filter": "(uid=x)"}).status_code == 422


# SSO (OpenID Connect)

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())) | {
    "kid": "k1",
    "alg": "RS256",
}


class Idp:
    """A fake identity provider behind httpx.MockTransport."""

    def __init__(self):
        self.claims: dict = {}
        self.alg = "RS256"

    def token(self, nonce: str) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": "monicomm",
            "sub": "u-1",
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            "preferred_username": "Dana",
            "name": "Dana Cohen",
            "email": "dana@corp.example",
            "groups": ["monicomm-admins"],
        } | self.claims
        if self.alg == "none":
            return jwt.encode(claims, None, algorithm="none")
        return jwt.encode(claims, KEY, algorithm=self.alg, headers={"kid": "k1"})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/certs",
                },
            )
        if path.endswith("/certs"):
            return httpx.Response(200, json={"keys": [JWK]})
        if path.endswith("/token"):
            form = parse_qs(request.content.decode())
            assert form["code_verifier"] and form["client_secret"] == ["s3cret"]
            return httpx.Response(200, json={"id_token": self.token(self.nonce)})
        return httpx.Response(404)


@pytest.fixture
def idp(monkeypatch):
    for key, value in {
        "SSO_ISSUER": ISSUER,
        "SSO_CLIENT_ID": "monicomm",
        "SSO_CLIENT_SECRET": "s3cret",
        "SSO_ADMIN_GROUP": "monicomm-admins",
        "SSO_DEFAULT_ROLE": "none",
        "SSO_LABEL": "Corp SSO",
    }.items():
        monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    fake = Idp()
    monkeypatch.setattr(sso, "_transport", httpx.MockTransport(fake))
    return fake


def sso_login(client, idp, state=None):
    start = client.get("/api/v1/auth/sso/start", follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    idp.nonce = query["nonce"][0]
    return client.get(
        "/api/v1/auth/sso/callback",
        params={"code": "abc", "state": state or query["state"][0]},
        follow_redirects=False,
    )


def test_sso_sign_in(client, idp):
    assert client.get("/api/v1/auth/methods").json()["sso"] == {"label": "Corp SSO"}
    res = sso_login(client, idp)
    assert res.headers["location"] == "/"
    assert client.get("/api/v1/auth/me").json() == {
        "name": "dana",
        "role": "admin",
        "display_name": "Dana Cohen",
        "email": "dana@corp.example",
        "source": "sso",
    }


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"claims": {"aud": "someone-else"}}, "/?sso=failed"),
        ({"claims": {"nonce": "replayed"}}, "/?sso=failed"),
        ({"claims": {"iss": "https://idp.corp.example/realms/other"}}, "/?sso=failed"),
        ({"claims": {"exp": int(time.time()) - 3600}}, "/?sso=failed"),
        ({"alg": "none"}, "/?sso=failed"),
        ({"claims": {"groups": ["staff"]}}, "/?sso=not_allowed"),
    ],
)
def test_sso_refuses_bad_tokens_and_users_without_a_group(client, idp, change, expected):
    idp.claims = change.get("claims", {})
    idp.alg = change.get("alg", "RS256")
    assert sso_login(client, idp).headers["location"] == expected
    assert client.get("/api/v1/auth/me").status_code == 401


def test_sso_state_must_come_back_to_the_same_browser(client, idp):
    assert sso_login(client, idp, state="forged").headers["location"] == "/?sso=failed"
    client.cookies.clear()
    res = client.get("/api/v1/auth/sso/callback?code=abc&state=x", follow_redirects=False)
    assert res.headers["location"] == "/?sso=failed"


SSO_FORM = {"issuer": ISSUER, "client_id": "monicomm", "client_secret": "s3cret", "label": "Corp"}


def test_sso_test_connection_and_settings(client, idp):
    admin(client)
    test = "/api/v1/admin/auth/sso/test"
    assert client.post(test, json=SSO_FORM).json()["ok"] is True
    public = client.post(test, json=SSO_FORM | {"issuer": "https://login.example.com"})
    assert public.json()["detail"] == "external_url"
    view = client.put("/api/v1/admin/auth/sso", json=SSO_FORM).json()
    assert view["callback_url"] == "http://testserver/api/v1/auth/sso/callback"
    assert view["label"] == "Corp" and "client_secret" not in view


def test_sso_test_connection_reports_an_unreachable_provider(client, monkeypatch):
    monkeypatch.setattr(sso, "_transport", httpx.MockTransport(lambda r: httpx.Response(500)))
    admin(client)
    res = client.post("/api/v1/admin/auth/sso/test", json=SSO_FORM).json()
    assert res == {"ok": False, "error": "unreachable", "user": None}

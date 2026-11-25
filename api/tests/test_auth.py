import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import get_settings
from app.main import app

ADMIN = {"localId": "uid-1", "email": "admin@monicomm.local", "emailVerified": False}
REAL_CLIENT = httpx.AsyncClient


@pytest.fixture
def client(monkeypatch):
    for key, value in {
        "ENV": "dev",
        "DEMO_DATA": "true",
        "AUTH_PROVIDER": "firebase",
        "FIREBASE_API_KEY": "web-key",
        "FIREBASE_AUTH_DOMAIN": "x.example",
        "FIREBASE_PROJECT_ID": "x",
        "ADMIN_UIDS": "uid-1",
        "ADMIN_EMAILS": "Boss@example.com",
    }.items():
        monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    auth._sessions.clear()
    yield TestClient(app)
    auth._sessions.clear()
    get_settings.cache_clear()


def firebase(monkeypatch, account):
    async def fake(_token, _key):
        if isinstance(account, Exception):
            raise account
        return account

    monkeypatch.setattr(auth, "lookup", fake)


def login(client):
    return client.post("/api/v1/auth/session", json={"id_token": "t"})


def test_everything_but_health_and_login_needs_a_session(client):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/auth/config").status_code == 200
    for path in ("dashboard/summary", "modules", "auth/me", "pcap/captures"):
        assert client.get(f"/api/v1/{path}").status_code == 401
    assert client.get("/api/docs").status_code == 401
    assert client.post("/api/v1/chat", json={}).status_code == 401
    assert client.get("/api/v1/dashboard/summary", cookies={auth.COOKIE: "x"}).status_code == 401


def test_listed_admin_signs_in_and_out(client, monkeypatch):
    firebase(monkeypatch, ADMIN)
    res = login(client)
    assert res.json() == {"name": "admin@monicomm.local", "role": "admin"}
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/dashboard/summary").status_code == 200
    saved = client.cookies[auth.COOKIE]
    assert client.delete("/api/v1/auth/session").status_code == 204
    res = client.get("/api/v1/dashboard/summary", cookies={auth.COOKIE: saved})
    assert res.status_code == 401


@pytest.mark.parametrize(
    "account,status",
    [
        ({"localId": "stranger", "email": "s@example.com", "emailVerified": True}, 403),
        ({"localId": "x", "email": "boss@example.com", "emailVerified": False}, 403),
        ({"localId": "x", "email": "boss@example.com", "emailVerified": True}, 200),
        ({"localId": "uid-1", "disabled": True}, 403),
        ({"email": ""}, 403),
        (None, 401),
        (auth.AuthUnavailable("x"), 503),
    ],
)
def test_who_may_enter(client, monkeypatch, account, status):
    firebase(monkeypatch, account)
    assert login(client).status_code == status


def test_session_expires(client, monkeypatch):
    firebase(monkeypatch, ADMIN)
    login(client)
    monkeypatch.setattr(auth.time, "monotonic", lambda: 10**12)
    assert client.get("/api/v1/auth/me").status_code == 401
    auth.open_session(auth.User(name="n", role="admin"))
    assert len(auth._sessions) == 1  # the expired one is gone


def test_session_count_is_bounded(client, monkeypatch):
    monkeypatch.setattr(auth, "MAX_SESSIONS", 2)
    for _ in range(4):
        auth.open_session(auth.User(name="n", role="admin"))
    assert len(auth._sessions) == 2


@pytest.mark.parametrize(
    "key,value",
    [("ENV", "prod"), ("AUTH_PROVIDER", "other"), ("FIREBASE_API_KEY", "")],
)
def test_unsafe_settings_stop_the_app(client, monkeypatch, key, value):
    monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError), TestClient(app):
        pass


def test_login_off_keeps_the_api_as_it_was(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "none")
    get_settings.cache_clear()
    assert client.get("/api/v1/modules").status_code == 200
    assert client.get("/api/v1/auth/config").status_code == 404
    assert login(client).status_code == 404


@pytest.mark.parametrize(
    "reply,expected",
    [
        (httpx.Response(200, json={"users": [ADMIN]}), ADMIN),
        (httpx.Response(200, json={}), None),
        (httpx.Response(400, json={"error": {}}), None),
    ],
)
def test_lookup(monkeypatch, reply, expected):
    seen = []

    def handler(request):
        seen.append(request)
        return reply

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_: REAL_CLIENT(transport=transport))
    assert asyncio.run(auth.lookup("tok", "key-1")) == expected
    assert "key-1" not in str(seen[0].url) and "tok" not in str(seen[0].url)


def test_lookup_failure_is_unavailable(monkeypatch):
    transport = httpx.MockTransport(lambda _r: httpx.Response(500))
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_: REAL_CLIENT(transport=transport))
    with pytest.raises(auth.AuthUnavailable):
        asyncio.run(auth.lookup("tok", "k"))

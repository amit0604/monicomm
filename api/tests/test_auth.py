import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import create_user
from app.core import auth, users
from app.core.config import get_settings
from app.main import app

PASSWORD = "correct-horse-1"


@pytest.fixture
def path(tmp_path):
    return tmp_path / "auth" / "users.json"


@pytest.fixture
def client(monkeypatch, path):
    monkeypatch.setitem(users.SCRYPT, "n", 16)  # fast hashes
    for key, value in {
        "ENV": "dev",
        "DEMO_DATA": "true",
        "AUTH_PROVIDER": "local",
        "USERS_FILE": str(path),
    }.items():
        monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    auth._sessions.clear()
    auth._failures.clear()
    users.add(get_settings(), users.NewUser(name="admin", role="admin", password=PASSWORD))
    yield TestClient(app)
    auth._sessions.clear()
    auth._failures.clear()
    get_settings.cache_clear()


def login(client, name="admin", password=PASSWORD):
    return client.post("/api/v1/auth/session", json={"name": name, "password": password})


def test_everything_but_health_and_login_needs_a_session(client):
    assert client.get("/api/v1/health").status_code == 200
    for path in ("dashboard/summary", "modules", "auth/me", "pcap/captures", "admin/users"):
        assert client.get(f"/api/v1/{path}").status_code == 401
    assert client.get("/api/docs").status_code == 401
    assert client.post("/api/v1/chat", json={}).status_code == 401
    client.cookies.set(auth.COOKIE, "x")
    assert client.get("/api/v1/dashboard/summary").status_code == 401


def test_sign_in_and_out(client):
    res = login(client, " Admin ")
    assert res.json() == {"name": "admin", "role": "admin"}
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" not in cookie
    assert client.get("/api/v1/dashboard/summary").status_code == 200
    saved = client.cookies[auth.COOKIE]
    assert client.delete("/api/v1/auth/session").status_code == 204
    client.cookies.set(auth.COOKIE, saved)
    assert client.get("/api/v1/dashboard/summary").status_code == 401


def test_secure_cookie_when_configured(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    assert "secure" in login(client).headers["set-cookie"].lower()


@pytest.mark.parametrize("name,password", [("admin", "wrong"), ("nobody", PASSWORD)])
def test_wrong_credentials_look_the_same(client, name, password):
    res = login(client, name, password)
    assert res.status_code == 401 and res.json() == {"detail": "wrong_credentials"}


def test_file_holds_hashes_only(client, path):
    text = path.read_text("utf-8")
    assert PASSWORD not in text and "scrypt$" in text
    users.add(get_settings(), users.NewUser(name="b", role="viewer", password=PASSWORD))
    hashes = {u["password_hash"] for u in json.loads(path.read_text("utf-8"))["users"]}
    assert len(hashes) == 2  # salted


def test_guessing_is_limited_then_released(client, monkeypatch):
    for _ in range(auth.MAX_FAILURES):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 429
    assert login(client, "other", "x").status_code == 401  # other names are not affected
    now = auth.time.monotonic()
    monkeypatch.setattr(auth.time, "monotonic", lambda: now + auth.FAILURE_SECONDS + 1)
    assert login(client).status_code == 200


def test_parallel_guesses_do_not_slip_past_the_limit(client):
    with ThreadPoolExecutor(10) as pool:
        codes = list(pool.map(lambda _: login(client, password="wrong").status_code, range(10)))
    assert codes.count(401) == auth.MAX_FAILURES


def test_tracked_names_are_bounded(client, monkeypatch):
    monkeypatch.setattr(auth, "MAX_TRACKED_NAMES", 3)
    for i in range(6):
        auth._take_attempt(f"n{i}")
    assert len(auth._failures) == 3


def test_session_expires_and_count_is_bounded(client, monkeypatch):
    login(client)
    user = users.find(get_settings(), "admin")
    monkeypatch.setattr(auth, "MAX_SESSIONS", 2)
    for _ in range(4):
        auth.open_session(user)
    assert len(auth._sessions) == 2
    monkeypatch.setattr(auth.time, "monotonic", lambda: 10**12)
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("content", ["{", '{"users": [{"name": "admin"}]}', b"\xff"])
def test_damaged_file_lets_nobody_in_and_is_not_overwritten(client, path, content):
    login(client)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 401
    before = path.read_bytes()
    with pytest.raises(users.UsersError, match="damaged"):
        users.add(get_settings(), users.NewUser(name="x", role="admin", password=PASSWORD))
    assert path.read_bytes() == before


def test_bad_stored_hash_never_matches(client, path):
    path.write_text('{"users":[{"name":"admin","role":"admin","password_hash":"x"}]}')
    assert login(client).status_code == 401


def test_missing_file_means_no_users(client, path):
    path.unlink()
    assert login(client).status_code == 401


def test_works_in_production(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "prod")
    get_settings.cache_clear()
    with TestClient(app) as prod:
        assert login(prod).status_code == 200


def test_unknown_provider_stops_the_app(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "firebase")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError), TestClient(app):
        pass


def test_login_off_keeps_the_api_as_it_was(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "none")
    get_settings.cache_clear()
    assert client.get("/api/v1/modules").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 404
    assert login(client).status_code == 404


@pytest.mark.parametrize(
    "argv,typed,code",
    [
        (["boss"], [PASSWORD, PASSWORD], 0),
        (["tech", "technician"], [PASSWORD, PASSWORD], 0),
        (["boss"], [PASSWORD, "other"], 1),
        (["boss"], ["short", "short"], 1),
        (["bad name"], [PASSWORD, PASSWORD], 1),
        (["boss", "king"], [PASSWORD, PASSWORD], 1),
        (["admin"], [PASSWORD, PASSWORD], 1),
        ([], [], 2),
    ],
)
def test_create_user_command(client, monkeypatch, argv, typed, code):
    answers = iter(typed)
    monkeypatch.setattr(create_user.getpass, "getpass", lambda _p: next(answers))
    assert create_user.main(argv) == code
    if code == 0:
        assert login(client, argv[0]).json()["name"] == argv[0]

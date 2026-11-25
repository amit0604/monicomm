import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import get_settings
from app.main import app

URL = "/api/v1/admin/emails"


@pytest.fixture
def anonymous(monkeypatch, tmp_path):
    for key, value in {
        "ENV": "dev",
        "AUTH_PROVIDER": "firebase",
        "FIREBASE_API_KEY": "web-key",
        "FIREBASE_AUTH_DOMAIN": "x.example",
        "FIREBASE_PROJECT_ID": "x",
        "ADMIN_UIDS": "uid-1",
        "ADMIN_EMAILS": "Env@example.com",
        "ADMIN_EMAILS_FILE": str(tmp_path / "admins.json"),
    }.items():
        monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    auth._sessions.clear()
    yield TestClient(app)
    auth._sessions.clear()
    get_settings.cache_clear()


@pytest.fixture
def client(anonymous):
    anonymous.cookies.set(auth.COOKIE, auth.open_session(auth.User(name="A", role="admin")))
    return anonymous


def put(client, *emails):
    return client.put(URL, json={"emails": list(emails)})


def google_login(monkeypatch, email, verified=True, uid="u"):
    async def fake(_token, _key):
        return {"localId": uid, "email": email, "emailVerified": verified}

    monkeypatch.setattr(auth, "lookup", fake)
    other = TestClient(app)
    return other, other.post("/api/v1/auth/session", json={"id_token": "t"}).status_code


def test_needs_an_admin_session(anonymous, monkeypatch):
    assert anonymous.get(URL).status_code == 401
    assert put(anonymous, "a@b.co").status_code == 401
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "none")
    get_settings.cache_clear()
    assert put(anonymous, "a@b.co").status_code == 403


def test_added_email_joins_the_env_ones(client, monkeypatch):
    assert google_login(monkeypatch, "new@example.com")[1] == 403
    res = put(client, " New@Example.com ", "new@example.com")
    assert res.json() == {"env": ["env@example.com"], "saved": ["new@example.com"]}
    assert client.get(URL).json() == res.json()
    assert google_login(monkeypatch, "NEW@example.com")[1] == 200
    assert google_login(monkeypatch, "env@example.com")[1] == 200
    assert google_login(monkeypatch, "new@example.com", verified=False)[1] == 403


def test_removed_email_loses_access_at_once(client, monkeypatch):
    put(client, "new@example.com")
    other, _ = google_login(monkeypatch, "new@example.com")
    assert other.get("/api/v1/auth/me").status_code == 200
    put(client)
    assert other.get("/api/v1/auth/me").status_code == 401
    assert client.get(URL).status_code == 200  # the admin by user id stays


def test_admin_by_user_id_does_not_depend_on_the_list(client, monkeypatch):
    other, status = google_login(monkeypatch, "x@example.com", verified=False, uid="uid-1")
    assert status == 200
    put(client)
    assert other.get("/api/v1/auth/me").status_code == 200


@pytest.mark.parametrize(
    "email",
    ["", "x", "a@b", "a b@c.co", "a@b.co,c@d.co", "a@b@c.co", "א@b.co", "a" * 250 + "@b.co"],
)
def test_bad_emails_are_refused_and_nothing_changes(client, email):
    put(client, "keep@example.com")
    assert put(client, "ok@example.com", email).status_code == 422
    assert client.get(URL).json()["saved"] == ["keep@example.com"]


def test_too_many_emails_are_refused(client):
    assert put(client, *(f"a{i}@b.co" for i in range(51))).status_code == 422


def test_damaged_file_adds_nobody(client, monkeypatch, tmp_path):
    (tmp_path / "admins.json").write_text('{"emails": "new@example.com"')
    assert client.get(URL).json()["saved"] == []
    assert google_login(monkeypatch, "new@example.com")[1] == 403


def test_save_failure_is_reported(client, monkeypatch, tmp_path):
    monkeypatch.setenv("MONICOMM_ADMIN_EMAILS_FILE", str(tmp_path / "missing" / "x.json"))
    get_settings.cache_clear()
    assert put(client, "a@b.co").status_code == 500

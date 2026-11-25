import pytest
from fastapi.testclient import TestClient

from app.core import auth, users
from app.core.config import get_settings
from app.main import app

URL = "/api/v1/admin/users"
PASSWORD = "correct-horse-1"


@pytest.fixture
def anonymous(monkeypatch, tmp_path):
    monkeypatch.setitem(users.SCRYPT, "n", 16)  # fast hashes
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "local")
    monkeypatch.setenv("MONICOMM_USERS_FILE", str(tmp_path / "users.json"))
    get_settings.cache_clear()
    auth._sessions.clear()
    auth._failures.clear()
    users.add(get_settings(), users.NewUser(name="admin", role="admin", password=PASSWORD))
    yield TestClient(app)
    auth._sessions.clear()
    auth._failures.clear()
    get_settings.cache_clear()


def login(name, password=PASSWORD):
    other = TestClient(app)
    res = other.post("/api/v1/auth/session", json={"name": name, "password": password})
    return other, res.status_code


@pytest.fixture
def client(anonymous):
    return login("admin")[0]


def add(client, name, role="technician", password=PASSWORD):
    return client.post(URL, json={"name": name, "role": role, "password": password})


def signed_in(client):
    return client.get("/api/v1/auth/me").status_code == 200


def test_needs_an_admin(client, anonymous, monkeypatch):
    assert anonymous.get(URL).status_code == 401
    add(client, "tech")
    tech, _ = login("tech")
    assert tech.get(URL).status_code == 403
    assert add(tech, "x", "admin").status_code == 403
    assert tech.delete(f"{URL}/admin").status_code == 403
    assert tech.put(f"{URL}/admin/password", json={"password": PASSWORD}).status_code == 403
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "none")
    get_settings.cache_clear()
    assert add(client, "y").status_code == 403


def test_add_lists_without_hashes(client):
    res = add(client, " Dana@Example.com ", "admin")
    assert res.json() == [
        {"name": "admin", "role": "admin"},
        {"name": "dana@example.com", "role": "admin"},
    ]
    assert client.get(URL).json() == res.json()
    assert login("DANA@example.com")[1] == 200


def test_removed_user_is_signed_out_at_once(client):
    add(client, "tech")
    tech, _ = login("tech")
    assert signed_in(tech)
    assert client.delete(f"{URL}/tech").status_code == 200
    assert not signed_in(tech)
    assert login("tech")[1] == 401


def test_new_password_signs_out_and_replaces_the_old(client):
    add(client, "tech")
    tech, _ = login("tech")
    res = client.put(f"{URL}/tech/password", json={"password": "another-pass-2"})
    assert res.status_code == 204
    assert not signed_in(tech)
    assert login("tech")[1] == 401
    assert login("tech", "another-pass-2")[1] == 200


def test_last_admin_stays(client):
    add(client, "tech")
    res = client.delete(f"{URL}/admin")
    assert res.status_code == 409 and res.json()["detail"] == "last_admin"
    add(client, "second", "admin")
    assert client.delete(f"{URL}/admin").status_code == 200
    assert not signed_in(client)


def test_refusals(client, monkeypatch):
    assert add(client, "ADMIN").json()["detail"] == "exists"
    assert client.delete(f"{URL}/ghost").status_code == 404
    assert client.put(f"{URL}/ghost/password", json={"password": PASSWORD}).status_code == 404
    monkeypatch.setattr(users, "MAX_USERS", 1)
    assert add(client, "x").json()["detail"] == "too_many"


@pytest.mark.parametrize(
    "name,role,password",
    [
        ("", "admin", PASSWORD),
        ("a b", "admin", PASSWORD),
        ("a/b", "admin", PASSWORD),
        ("דנה", "admin", PASSWORD),
        ("x" * 65, "admin", PASSWORD),
        ("x", "king", PASSWORD),
        ("x", "admin", "short"),
        ("x", "admin", "p" * 201),
    ],
)
def test_bad_input_changes_nothing(client, name, role, password):
    assert add(client, name, role, password).status_code == 422
    assert len(client.get(URL).json()) == 1


def test_save_failure_is_reported(client, monkeypatch):
    def fail(*_args):
        raise OSError

    monkeypatch.setattr(users.os, "replace", fail)
    assert add(client, "x").status_code == 500


def test_damaged_file_is_reported(client, monkeypatch):
    def damaged(_settings):
        raise users.UsersError("damaged")

    admin = users.find(get_settings(), "admin")
    monkeypatch.setattr(users, "find", lambda _s, _n: admin)
    monkeypatch.setattr(users, "load", damaged)
    assert client.get(URL).status_code == 500
    assert add(client, "x").status_code == 500
    assert client.delete(f"{URL}/admin").status_code == 500
    assert client.put(f"{URL}/admin/password", json={"password": PASSWORD}).status_code == 500

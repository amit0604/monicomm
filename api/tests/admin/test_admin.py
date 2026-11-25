import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import llm_client, llm_settings
from app.core import auth, users
from app.core.config import get_settings
from app.main import app

URL = "/api/v1/admin/llm"
KEY = "secret-key-123"
FORM = {
    "provider": "gemini",
    "base_url": "http://llm:11434/",
    "model": "qwen2.5:7b",
    "gemini_model": "gemini-2.5-flash",
}
REAL_CLIENT = httpx.AsyncClient


@pytest.fixture
def anonymous(monkeypatch, tmp_path):
    monkeypatch.setitem(users.SCRYPT, "n", 16)  # fast hashes
    for key, value in {
        "ENV": "dev",
        "DEMO_DATA": "true",
        "AUTH_PROVIDER": "local",
        "USERS_FILE": str(tmp_path / "users.json"),
        "LLM_PROVIDER": "ollama",
        "GEMINI_API_KEY": "",
        "LLM_SETTINGS_FILE": str(tmp_path / "llm.json"),
    }.items():
        monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    auth._sessions.clear()
    yield TestClient(app)
    auth._sessions.clear()
    get_settings.cache_clear()


@pytest.fixture
def client(anonymous):
    users.add(get_settings(), users.NewUser(name="admin", role="admin", password="long-password"))
    token = auth.open_session(users.find(get_settings(), "admin"))
    anonymous.cookies.set(auth.COOKIE, token)
    return anonymous


def model_replies(monkeypatch, reply):
    seen = []

    def handler(request):
        seen.append(request)
        return reply

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        llm_client.httpx, "AsyncClient", lambda **_: REAL_CLIENT(transport=transport)
    )
    return seen


def gemini_ok():
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})


def test_needs_a_session(anonymous):
    for method, path in (("GET", URL), ("PUT", URL), ("DELETE", URL), ("POST", f"{URL}/test")):
        assert anonymous.request(method, path, json=FORM).status_code == 401


def test_closed_when_login_is_off(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_AUTH_PROVIDER", "none")
    get_settings.cache_clear()
    assert client.get(URL).status_code == 403
    assert client.put(URL, json=FORM | {"api_key": KEY}).status_code == 403


def test_closed_outside_dev(client, monkeypatch, tmp_path):
    monkeypatch.setenv("MONICOMM_ENV", "prod")
    get_settings.cache_clear()
    for method, path in (("GET", URL), ("PUT", URL), ("DELETE", URL), ("POST", f"{URL}/test")):
        res = client.request(method, path, json=FORM | {"api_key": KEY})
        assert (res.status_code, res.json()["detail"]) == (403, "dev_only")
    assert not (tmp_path / "llm.json").exists()


def test_saves_the_key_and_never_returns_it(client):
    assert client.get(URL).json()["key_source"] == "none"
    res = client.put(URL, json=FORM | {"api_key": KEY})
    assert res.json()["key_source"] == "saved" and KEY not in res.text
    assert KEY not in client.get(URL).text
    now = llm_settings.current()
    assert (now.llm_provider, now.gemini_api_key) == ("gemini", KEY)
    assert now.llm_base_url == "http://llm:11434"


def test_saving_without_a_key_keeps_it_and_reset_removes_it(client):
    client.put(URL, json=FORM | {"api_key": KEY})
    client.put(URL, json=FORM | {"gemini_model": "gemini-x"})
    now = llm_settings.current()
    assert (now.gemini_model, now.gemini_api_key) == ("gemini-x", KEY)
    assert client.delete(URL).json()["saved"] is False
    assert llm_settings.current().gemini_api_key == ""


def test_key_from_env_is_used_until_one_is_saved(client, monkeypatch):
    monkeypatch.setenv("MONICOMM_GEMINI_API_KEY", "env-key")
    get_settings.cache_clear()
    assert client.put(URL, json=FORM).json()["key_source"] == "env"
    assert llm_settings.current().gemini_api_key == "env-key"


@pytest.mark.parametrize("key,value", [("ENV", "prod"), ("AUTH_PROVIDER", "none")])
def test_saved_values_are_ignored_outside_dev_login(client, monkeypatch, key, value):
    client.put(URL, json=FORM | {"api_key": KEY})
    monkeypatch.setenv(f"MONICOMM_{key}", value)
    get_settings.cache_clear()
    assert llm_settings.current().llm_provider == "ollama"
    assert llm_settings.current().gemini_api_key == ""


def test_damaged_file_falls_back_to_env(client, tmp_path):
    (tmp_path / "llm.json").write_text("{oops")
    assert client.get(URL).json()["saved"] is False


@pytest.mark.parametrize(
    "change,status",
    [
        ({}, 400),  # gemini without any key
        ({"api_key": KEY, "base_url": "https://llm.example.com"}, 400),
        ({"api_key": KEY, "base_url": "http://[bad"}, 400),
        ({"api_key": "has space"}, 422),
        ({"api_key": ""}, 422),
        ({"api_key": KEY, "gemini_model": "../x"}, 422),
        ({"provider": "openai"}, 422),
    ],
)
def test_bad_values_are_refused(client, change, status):
    assert client.put(URL, json=FORM | change).status_code == status
    assert client.get(URL).json()["saved"] is False


def test_save_failure_is_reported(client, monkeypatch):
    def fail(*_):
        raise OSError

    monkeypatch.setattr(llm_settings, "save", fail)
    assert client.put(URL, json=FORM | {"api_key": KEY}).status_code == 500


def test_connection_test_uses_the_new_key_without_saving(client, monkeypatch):
    seen = model_replies(monkeypatch, gemini_ok())
    res = client.post(f"{URL}/test", json=FORM | {"api_key": KEY})
    assert res.json() == {"ok": True, "error": None}
    assert seen[0].headers["x-goog-api-key"] == KEY
    assert client.get(URL).json()["saved"] is False


@pytest.mark.parametrize(
    "status,error",
    [
        (400, "key_rejected"),
        (403, "key_rejected"),
        (404, "model_not_found"),
        (429, "rate_limited"),
        (500, "unavailable"),
    ],
)
def test_connection_test_explains_failure(client, monkeypatch, status, error):
    model_replies(monkeypatch, httpx.Response(status))
    res = client.post(f"{URL}/test", json=FORM | {"api_key": KEY})
    assert res.json() == {"ok": False, "error": error} and KEY not in res.text


def test_connection_test_without_a_key(client):
    assert client.post(f"{URL}/test", json=FORM).json()["error"] == "key_missing"


def test_chat_uses_the_saved_key(client, monkeypatch):
    seen = model_replies(monkeypatch, gemini_ok())
    client.put(URL, json=FORM | {"api_key": KEY})
    body = {"messages": [{"role": "user", "content": "Which devices are down?"}]}
    res = client.post("/api/v1/chat", json=body)
    assert res.status_code == 200 and res.json()["model"] == "gemini-2.5-flash"
    assert seen[0].headers["x-goog-api-key"] == KEY

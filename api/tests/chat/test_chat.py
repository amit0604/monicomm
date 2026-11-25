import json

import pytest
from fastapi.testclient import TestClient

from app.ai import llm_client
from app.core.config import get_settings
from app.main import app
from app.modules.chat import service
from app.modules.dashboard.demo import DemoSource
from app.modules.dashboard.router import source_or_503

client = TestClient(app)
URL = "/api/v1/chat"


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "dev")
    monkeypatch.setenv("MONICOMM_DEMO_DATA", "true")
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "ollama")
    get_settings.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def calls(monkeypatch):
    seen = []

    async def fake(messages):
        seen.append(messages)
        return " answer "

    monkeypatch.setattr(llm_client, "chat", fake)
    return seen


def user(text):
    return {"role": "user", "content": text}


def bot(text):
    return {"role": "assistant", "content": text}


def post(*messages):
    return client.post(URL, json={"messages": list(messages)})


def test_model_gets_current_records_marked_demo(calls):
    res = post(user("מה מצב הרשת כרגע?"))
    assert res.status_code == 200
    assert res.json()["source"] == "demo"
    assert res.json()["reply"] == "answer"
    system, sent = calls[0][0], calls[0][-1]["content"]
    assert system["role"] == "system" and "read-only" in system["content"]
    for text in (
        "DEMO - fabricated",
        "DEMO-edge-rtr-02",
        "high_temperature",
        "ENVMON-2-TEMP",
        "temperature_c",
        "מה מצב הרשת כרגע?",
    ):
        assert text in sent


def test_follow_up_keeps_conversation_with_data_on_newest_question_only(calls):
    post(user("first"), bot("old"), user("second"))
    assert calls[0][1:3] == [user("first"), bot("old")]
    assert "MONICOMM_DATA" in calls[0][3]["content"]
    assert calls[0][3]["content"].endswith("second")


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [bot("x")],
        [user("a"), bot("b")],
        [user("a"), user("b"), user("c")],
        [{"role": "system", "content": "x"}],
        [user(" ")],
        [user("x" * 2001)],
    ],
)
def test_bad_conversations_are_refused(calls, messages):
    assert post(*messages).status_code == 400
    assert calls == []


def test_body_limits(calls):
    assert client.post(URL, json={"messages": [], "pad": "x" * 600_000}).status_code == 413
    assert client.post(URL, content=b"{", headers={"content-type": "text/plain"}).status_code == 415


def test_long_history_drops_oldest_pairs():
    messages = [
        service.Message(role="assistant" if i % 2 else "user", content=f"m{i}") for i in range(41)
    ]
    kept = service.prepare_history(messages)
    assert len(kept) == 21
    assert kept[0].role == "user" and kept[-1].content == "m40"


class LiveSource(DemoSource):
    source = "live"


def test_external_model_never_sees_live_data(calls, monkeypatch):
    app.dependency_overrides[source_or_503] = LiveSource
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "gemini")
    get_settings.cache_clear()
    res = post(user("x"))
    assert res.status_code == 503 and res.json()["detail"] == "not_allowed"
    assert calls == []


def test_local_model_may_see_live_data(calls):
    app.dependency_overrides[source_or_503] = LiveSource
    assert post(user("x")).json()["source"] == "live"


@pytest.mark.parametrize(
    "error,detail",
    [
        (llm_client.LLMUnavailable("secret detail"), "llm_unavailable"),
        (llm_client.ExternalEndpointError("secret detail"), "not_allowed"),
    ],
)
def test_model_errors_become_clean_codes(monkeypatch, error, detail):
    async def fail(_messages):
        raise error

    monkeypatch.setattr(llm_client, "chat", fail)
    res = post(user("x"))
    assert res.status_code == 503 and res.json() == {"detail": detail}


def test_empty_reply_is_unavailable(monkeypatch):
    async def empty(_messages):
        return "  "

    monkeypatch.setattr(llm_client, "chat", empty)
    assert post(user("x")).status_code == 503


def test_context_stays_in_limit_on_a_large_network():
    class Big(DemoSource):
        def devices(self):
            base = super().devices()
            return [base[i % len(base)].model_copy(update={"id": f"x{i}"}) for i in range(5000)]

        def device(self, device_id):
            return super().device("demo-1")

    text, context = service.collect_context(Big())
    assert len(text) <= service.MAX_CONTEXT_CHARS
    assert context.totals.devices == 5000
    assert 0 < context.included.devices < 5000
    assert json.loads(text)["devices"][0]["status"] == "critical"

import asyncio

import httpx
import pytest

from app.ai import llm_client
from app.ai.llm_client import ExternalEndpointError, validate_llm_url
from app.core.config import Settings, get_settings


@pytest.mark.parametrize(
    "url",
    [
        "http://llm:11434",
        "http://localhost:11434",
        "http://10.0.5.20:8000",
        "http://192.168.1.10:11434",
        "https://gpu01.lan:8000",
    ],
)
def test_internal_urls_are_allowed(url):
    assert validate_llm_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://api.anthropic.com",
        "http://8.8.8.8:11434",
        "ftp://llm:21",
        "not a url",
    ],
)
def test_external_or_invalid_urls_are_refused(url):
    with pytest.raises(ExternalEndpointError):
        validate_llm_url(url)


# --- chat() ---------------------------------------------------------------


def _patch_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def fake(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", fake)


def _set_url(monkeypatch, url):
    monkeypatch.setenv("MONICOMM_LLM_BASE_URL", url)
    get_settings.cache_clear()


def test_chat_returns_message_content(monkeypatch):
    _set_url(monkeypatch, "http://llm:11434")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"}})

    _patch_transport(monkeypatch, handler)
    out = asyncio.run(llm_client.chat([{"role": "user", "content": "x"}]))
    assert out == "hi"
    assert seen["url"] == "http://llm:11434/api/chat"
    assert b'"stream":false' in seen["body"].replace(b" ", b"")
    get_settings.cache_clear()


def test_chat_connection_error_raises_unavailable(monkeypatch):
    _set_url(monkeypatch, "http://llm:11434")

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    _patch_transport(monkeypatch, handler)
    with pytest.raises(llm_client.LLMUnavailable):
        asyncio.run(llm_client.chat([]))
    get_settings.cache_clear()


def test_chat_http_error_raises_unavailable(monkeypatch):
    _set_url(monkeypatch, "http://llm:11434")
    _patch_transport(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(llm_client.LLMUnavailable):
        asyncio.run(llm_client.chat([]))
    get_settings.cache_clear()


@pytest.mark.parametrize("body", [{"unexpected": True}, "not json"])
def test_chat_unusable_reply_raises_unavailable(monkeypatch, body):
    _set_url(monkeypatch, "http://llm:11434")
    reply = (
        (lambda r: httpx.Response(200, json=body))
        if isinstance(body, dict)
        else (lambda r: httpx.Response(200, text=body))
    )
    _patch_transport(monkeypatch, reply)
    with pytest.raises(llm_client.LLMUnavailable):
        asyncio.run(llm_client.chat([]))
    get_settings.cache_clear()


def test_chat_refuses_public_url_before_request(monkeypatch):
    _set_url(monkeypatch, "https://api.openai.com")  # airgap: allow
    calls = []
    _patch_transport(monkeypatch, lambda request: calls.append(request))
    with pytest.raises(ExternalEndpointError):
        asyncio.run(llm_client.chat([]))
    assert calls == []
    get_settings.cache_clear()


# --- dev-only gemini provider ------------------------------------------------


def _gemini(monkeypatch, env="dev", key="test-key"):
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("MONICOMM_ENV", env)
    monkeypatch.setenv("MONICOMM_GEMINI_API_KEY", key)
    get_settings.cache_clear()


def test_gemini_sends_key_in_header_and_system_instruction(monkeypatch):
    _gemini(monkeypatch)
    seen = {}

    def handler(request):
        seen["req"] = request
        reply = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        return httpx.Response(200, json=reply)

    _patch_transport(monkeypatch, handler)
    msgs = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "q"}]
    assert asyncio.run(llm_client.chat(msgs)) == "ok"
    req = seen["req"]
    assert req.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(req.url)
    body = req.read().decode()
    assert "systemInstruction" in body and "be brief" in body
    get_settings.cache_clear()


def test_gemini_refused_outside_dev(monkeypatch):
    _gemini(monkeypatch, env="prod")
    calls = []
    _patch_transport(monkeypatch, lambda request: calls.append(request))
    with pytest.raises(ExternalEndpointError):
        asyncio.run(llm_client.chat([]))
    assert calls == []
    get_settings.cache_clear()


def test_gemini_without_key_is_unavailable(monkeypatch):
    _gemini(monkeypatch, key="")
    with pytest.raises(llm_client.LLMUnavailable):
        asyncio.run(llm_client.chat([]))
    get_settings.cache_clear()


def test_gemini_error_does_not_leak_key(monkeypatch):
    _gemini(monkeypatch)
    _patch_transport(monkeypatch, lambda request: httpx.Response(403, text="denied"))
    with pytest.raises(llm_client.LLMUnavailable) as err:
        asyncio.run(llm_client.chat([{"role": "user", "content": "q"}]))
    assert "test-key" not in str(err.value)
    get_settings.cache_clear()


def test_unknown_provider_is_unavailable(monkeypatch):
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "nope")
    get_settings.cache_clear()
    with pytest.raises(llm_client.LLMUnavailable):
        asyncio.run(llm_client.chat([]))
    get_settings.cache_clear()


def test_gemini_refused_when_env_not_set(monkeypatch):
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("MONICOMM_GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("MONICOMM_ENV", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ExternalEndpointError):
        asyncio.run(llm_client.chat([]))
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("provider", "expected"), [("ollama", "qwen2.5:7b"), ("gemini", "gemini-2.5-flash")]
)
def test_model_name_follows_the_provider(provider, expected):
    settings = Settings(
        llm_provider=provider, llm_model="qwen2.5:7b", gemini_model="gemini-2.5-flash"
    )
    assert llm_client.model_name(settings) == expected

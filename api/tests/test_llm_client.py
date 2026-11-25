import pytest

from app.ai.llm_client import ExternalEndpointError, validate_llm_url


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


def _transport(handler):
    import httpx

    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), calls


def test_chat_posts_to_ollama_and_returns_content():
    import asyncio
    import json

    import httpx

    from app.ai.llm_client import chat

    transport, calls = _transport(
        lambda r: httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"}})
    )
    msgs = [{"role": "user", "content": "hello"}]
    assert asyncio.run(chat(msgs, transport=transport)) == "hi"
    body = json.loads(calls[0].content)
    assert calls[0].url.path == "/api/chat"
    assert body["messages"] == msgs and body["stream"] is False


@pytest.mark.parametrize(
    "response",
    [
        lambda httpx: httpx.Response(500, text="boom"),
        lambda httpx: httpx.Response(200, json={"unexpected": True}),
        lambda httpx: httpx.Response(200, text="not json"),
    ],
)
def test_chat_failures_raise_llm_error(response):
    import asyncio

    import httpx

    from app.ai.llm_client import LLMError, chat

    transport, _ = _transport(lambda r: response(httpx))
    with pytest.raises(LLMError):
        asyncio.run(chat([{"role": "user", "content": "x"}], transport=transport))


def test_chat_refuses_public_llm_url_before_any_request(monkeypatch):
    import asyncio

    import httpx

    from app.ai import llm_client
    from app.core.config import Settings

    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: Settings(llm_base_url="https://api.openai.com"),  # airgap: allow
    )
    transport, calls = _transport(lambda r: httpx.Response(200, json={}))
    with pytest.raises(llm_client.LLMError):
        asyncio.run(llm_client.chat([{"role": "user", "content": "x"}], transport=transport))
    assert calls == []

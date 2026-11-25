"""The single gateway to the local LLM (PROJECT.md section 3, AI design rule 1).

Every feature calls the model through this module. It only talks to hosts inside the
closed network: a public LLM endpoint is refused before any request is made.

DEV-ONLY EXCEPTION (PROJECT.md decision log): MONICOMM_LLM_PROVIDER=gemini sends prompts to
Google AI Studio for local development without a GPU. It only works when MONICOMM_ENV=dev, the
key comes from the local .env (never git), and the Docker api container can't reach it anyway
(internal network). Never enable it on the closed network.
"""

import ipaddress
from urllib.parse import urlparse

import httpx

from app.ai import llm_settings
from app.core.config import Settings


class ExternalEndpointError(ValueError):
    """Raised when the LLM URL points outside the closed network."""


class LLMUnavailable(RuntimeError):
    """Raised when the model server can't be reached or returns an error."""


def _is_internal_host(host: str) -> bool:
    # Docker service names and local names have no dots ("llm", "localhost") or end in .local/.lan
    if "." not in host or host.endswith((".local", ".lan", ".internal", ".localhost")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a public-looking DNS name such as api.example.com
    return ip.is_private or ip.is_loopback


def validate_llm_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ExternalEndpointError(f"Invalid LLM URL: {url!r}")
    if not _is_internal_host(parsed.hostname):
        raise ExternalEndpointError(
            f"LLM URL {url!r} is outside the closed network. Monicomm is air-gapped."
        )
    return url


def llm_base_url(settings: Settings | None = None) -> str:
    return validate_llm_url((settings or llm_settings.current()).llm_base_url)


# dev-only, see module docstring
GEMINI_HOST = "https://generativelanguage.googleapis.com"  # airgap: allow
GEMINI_URL = GEMINI_HOST + "/v1beta/models/{model}:generateContent"


async def chat(messages: list[dict], settings: Settings | None = None) -> str:
    """Send a chat to the configured model and return the reply text.

    `settings` is only for the Admin page, to test a connection before saving it.
    """
    settings = settings or llm_settings.current()
    if settings.llm_provider == "gemini":
        return await _gemini_chat(messages, settings)
    if settings.llm_provider != "ollama":
        raise LLMUnavailable(f"Unknown LLM provider {settings.llm_provider!r}")
    url = f"{llm_base_url(settings)}/api/chat"  # guard runs before any request
    body = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        raise LLMUnavailable(f"LLM call failed: {e}") from e


async def _gemini_chat(messages: list[dict], settings: Settings) -> str:
    if settings.env != "dev":
        raise ExternalEndpointError("The gemini provider is dev-only. Monicomm is air-gapped.")
    if not settings.gemini_api_key:
        raise LLMUnavailable("MONICOMM_GEMINI_API_KEY is not set")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    body = {
        "contents": [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
            if m["role"] != "system"
        ],
        "generationConfig": {"temperature": 0},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as client:
            resp = await client.post(
                GEMINI_URL.format(model=settings.gemini_model),
                json=body,
                headers={"x-goog-api-key": settings.gemini_api_key},  # header, never in the URL
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
        # don't echo the request (it carries the key header); status + type is enough
        raise LLMUnavailable(f"Gemini call failed: {type(e).__name__}") from e

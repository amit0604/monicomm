"""The single gateway to the local LLM (PROJECT.md section 3, AI design rule 1).

Every feature calls the model through this module. It only talks to hosts inside the
closed network: a public LLM endpoint is refused before any request is made.
"""

import ipaddress
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


class ExternalEndpointError(ValueError):
    """Raised when the LLM URL points outside the closed network."""


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


def llm_base_url() -> str:
    return validate_llm_url(get_settings().llm_base_url)


class LLMError(RuntimeError):
    """The model server failed or returned something unusable."""


async def chat(messages: list[dict], *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """One chat completion from the local model (Ollama /api/chat, non-streaming).

    `messages` are {"role": "system" | "user" | "assistant", "content": str}.
    `transport` is for tests only. Raises LLMError on any failure.
    """
    settings = get_settings()
    body = {"model": settings.llm_model, "messages": messages, "stream": False}
    try:
        async with httpx.AsyncClient(
            base_url=llm_base_url(), timeout=settings.llm_timeout_s, transport=transport
        ) as client:
            res = await client.post("/api/chat", json=body)
            res.raise_for_status()
            return res.json()["message"]["content"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        raise LLMError(f"LLM request failed: {type(e).__name__}") from e

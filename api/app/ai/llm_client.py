"""The single gateway to the local LLM (PROJECT.md section 3, AI design rule 1).

Every feature calls the model through this module. It only talks to hosts inside the
closed network: a public LLM endpoint is refused before any request is made.
"""

import ipaddress
from urllib.parse import urlparse

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

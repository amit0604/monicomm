"""The closed-network rule for every address the api connects to (CLAUDE.md rule 1).

Used for the model server, the LDAP server and the SSO identity provider. An address is inside
the closed network when it is a private or loopback IP, a single-label or .local/.lan/.internal
name, or a name under one of MONICOMM_INTERNAL_DOMAINS (for example the AD domain corp.example).
"""

import ipaddress
from urllib.parse import urlparse

from app.core.config import get_settings

_LOCAL_SUFFIXES = (".local", ".lan", ".internal", ".localhost")


class ExternalEndpointError(ValueError):
    """Raised when an address points outside the closed network."""


def internal_domains() -> tuple[str, ...]:
    raw = get_settings().internal_domains
    return tuple(d.strip().lower().strip(".") for d in raw.split(",") if d.strip())


def is_internal_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    if "." not in host or host.endswith(_LOCAL_SUFFIXES):
        return True
    if any(host == d or host.endswith("." + d) for d in internal_domains()):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a public-looking DNS name such as api.example.com
    return ip.is_private or ip.is_loopback


def check_url(url: str, schemes: set[str], what: str) -> str:
    """The URL unchanged, or ExternalEndpointError before anything is sent."""
    parsed = urlparse(url)
    if parsed.scheme not in schemes or not parsed.hostname:
        raise ExternalEndpointError(f"Invalid {what} URL: {url!r}")
    if not is_internal_host(parsed.hostname):
        raise ExternalEndpointError(
            f"{what} URL {url!r} is outside the closed network. Monicomm is air-gapped."
        )
    return url

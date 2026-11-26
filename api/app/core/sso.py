"""SSO over OpenID Connect: authorization code flow with PKCE, against an identity provider on
the closed network (on-prem AD FS, Keycloak...). Read-only toward the identity provider.

The browser goes to the identity provider and back to /api/v1/auth/sso/callback. The api then
trades the code for an ID token, checks its signature against the provider's published keys,
its issuer, audience, expiry and nonce, and maps the groups claim to a role.
"""

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.core.airgap import check_url
from app.core.auth_settings import SsoSettings, role_for
from app.core.config import get_settings

TIMEOUT_S = 10
STATE_SECONDS = 10 * 60
MAX_PENDING = 1000
# Signatures with the provider's public keys only: never "none" or a shared-secret HMAC.
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]

_pending: dict[str, tuple[str, str, float]] = {}  # state -> nonce, PKCE verifier, expiry
_lock = threading.Lock()
_transport: httpx.BaseTransport | None = None  # tests use httpx.MockTransport


class SsoError(RuntimeError):
    """code: incomplete, external_url, unreachable, bad_discovery, issuer_mismatch,
    state_mismatch, token_failed, invalid_token."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class NotAllowed(RuntimeError):
    """Signed in at the identity provider, but no group gives this user a role."""


@dataclass
class SsoUser:
    name: str
    display_name: str | None
    email: str | None
    role: str


def _schemes() -> set[str]:
    return {"https", "http"} if get_settings().env == "dev" else {"https"}


def _url(url: object, what: str = "SSO") -> str:
    if not isinstance(url, str):
        raise SsoError("bad_discovery")
    try:
        return check_url(url, _schemes(), what)
    except ValueError:
        raise SsoError("external_url") from None


def _client(cfg: SsoSettings) -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT_S,
        verify=cfg.ca_file or True,
        follow_redirects=False,
        transport=_transport,
    )


def _get_json(client: httpx.Client, url: str) -> dict:
    try:
        res = client.get(url, headers={"accept": "application/json"})
        res.raise_for_status()
        body = res.json()
    except (httpx.HTTPError, ValueError):
        raise SsoError("unreachable") from None
    if not isinstance(body, dict):
        raise SsoError("bad_discovery")
    return body


def discovery(cfg: SsoSettings) -> dict:
    if not cfg.enabled:
        raise SsoError("incomplete")
    issuer = _url(cfg.issuer.rstrip("/"))
    with _client(cfg) as client:
        doc = _get_json(client, issuer + "/.well-known/openid-configuration")
    if str(doc.get("issuer", "")).rstrip("/") != issuer:
        raise SsoError("issuer_mismatch")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        _url(doc.get(key))
    return doc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start(cfg: SsoSettings, redirect_uri: str) -> tuple[str, str]:
    """(where to send the browser, state). The state also goes into a cookie (see auth.py)."""
    doc = discovery(cfg)
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    now = time.monotonic()
    with _lock:
        for old in [s for s, (_, _, exp) in _pending.items() if exp <= now]:
            del _pending[old]
        while len(_pending) >= MAX_PENDING:
            del _pending[next(iter(_pending))]
        _pending[state] = (nonce, verifier, now + STATE_SECONDS)
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "scope": cfg.scopes or "openid",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    }
    endpoint = doc["authorization_endpoint"]
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(params)}", state


def _verify(client: httpx.Client, doc: dict, cfg: SsoSettings, id_token: str, nonce: str) -> dict:
    jwks = _get_json(client, doc["jwks_uri"])
    try:
        header = jwt.get_unverified_header(id_token)
        if header.get("alg") not in ALGORITHMS:
            raise SsoError("invalid_token")
        keys = jwt.PyJWKSet.from_dict(jwks).keys
        kid = header.get("kid")
        match = [k for k in keys if k.key_id == kid] if kid else keys
        if len(match) != 1:
            raise SsoError("invalid_token")
        claims = jwt.decode(
            id_token,
            match[0].key,
            algorithms=[header["alg"]],
            audience=cfg.client_id,
            issuer=doc["issuer"],
            leeway=60,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise SsoError("invalid_token") from None
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("invalid_token")
    return claims


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def finish(cfg: SsoSettings, code: str, state: str, redirect_uri: str) -> SsoUser:
    with _lock:
        pending = _pending.pop(state, None)
    if pending is None or pending[2] <= time.monotonic():
        raise SsoError("state_mismatch")
    nonce, verifier, _ = pending
    doc = discovery(cfg)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cfg.client_id,
        "code_verifier": verifier,
    }
    if cfg.client_secret:
        form["client_secret"] = cfg.client_secret
    with _client(cfg) as client:
        try:
            res = client.post(doc["token_endpoint"], data=form)
            body = res.json() if res.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            raise SsoError("unreachable") from None
        id_token = body.get("id_token") if isinstance(body, dict) else None
        if not isinstance(id_token, str):
            raise SsoError("token_failed")
        claims = _verify(client, doc, cfg, id_token, nonce)
    name = next(
        (
            v
            for v in map(_text, (claims.get(k) for k in ("preferred_username", "upn", "email")))
            if v
        ),
        str(claims["sub"]),
    )
    groups = claims.get(cfg.groups_claim) if cfg.groups_claim else None
    groups = groups if isinstance(groups, list) else [groups] if isinstance(groups, str) else []
    role = role_for(
        [str(g) for g in groups], cfg.admin_group, cfg.technician_group, cfg.default_role
    )
    if role is None:
        raise NotAllowed(name)
    return SsoUser(
        name=name.lower()[:64],
        display_name=_text(claims.get("name")),
        email=_text(claims.get("email")),
        role=role,
    )


def test_connection(cfg: SsoSettings) -> dict:
    """Read the provider's discovery document and its signing keys. Signs nobody in."""
    try:
        doc = discovery(cfg)
        with _client(cfg) as client:
            jwks = _get_json(client, doc["jwks_uri"])
        if not jwks.get("keys"):
            return {"ok": False, "error": "bad_discovery"}
    except SsoError as e:
        return {"ok": False, "error": e.code}
    return {"ok": True}

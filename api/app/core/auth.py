"""Login. No internet needed.

With MONICOMM_AUTH_PROVIDER=local every /api route except health and login needs a session.
Users sign in with a local account (core/users.py), an LDAP / Active Directory account
(core/ldap_auth.py) or SSO over OpenID Connect (core/sso.py). A local account with the same name
always wins, so a local admin can still get in when the directory or the identity provider is down.
"""

import logging
import secrets
import threading
import time
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core import auth_settings, ldap_auth, sso, users
from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)
COOKIE = "monicomm_session"
SSO_COOKIE = "monicomm_sso_state"
SSO_PATH = "/api/v1/auth/sso"
SESSION_SECONDS = 8 * 3600
MAX_SESSIONS = 1000
MAX_FAILURES = 5
FAILURE_SECONDS = 5 * 60
MAX_TRACKED_NAMES = 1000
OPEN_PATHS = (
    "/api/v1/health",
    "/api/v1/auth/session",
    "/api/v1/auth/me",
    "/api/v1/auth/methods",
    f"{SSO_PATH}/start",
    f"{SSO_PATH}/callback",
)


class User(BaseModel):
    name: str
    role: users.Role
    display_name: str | None = None
    email: str | None = None
    source: Literal["local", "ldap", "sso"] = "local"


class Credentials(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=users.MAX_PASSWORD)


# One api process; a restart signs everyone out.
# token -> user, stamp (a local user's password hash at sign in, else ""), expiry
_sessions: dict[str, tuple[User, str, float]] = {}
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def check_settings(settings: Settings) -> bool:
    """True when login is on. Raises on a configuration that must never start."""
    if settings.auth_provider == "none":
        return False
    if settings.auth_provider != "local":
        raise RuntimeError(f"Unknown MONICOMM_AUTH_PROVIDER {settings.auth_provider!r}")
    return True


def _open(user: User, stamp: str) -> str:
    now = time.monotonic()
    token = secrets.token_urlsafe(32)
    with _lock:
        for old in [t for t, (_, _, expires) in _sessions.items() if expires <= now]:
            del _sessions[old]
        while len(_sessions) >= MAX_SESSIONS:
            del _sessions[next(iter(_sessions))]  # the oldest
        _sessions[token] = (user, stamp, now + SESSION_SECONDS)
    return token


def open_session(user: users.StoredUser) -> str:
    """A local user's session; it ends when the user is removed or the password changes."""
    return _open(User(name=user.name, role=user.role), user.password_hash)


def open_external_session(user: User) -> str:
    """An LDAP or SSO user's session. The role is the one at sign in, for SESSION_SECONDS."""
    return _open(user, "")


def _close_session(request: Request) -> None:
    with _lock:
        _sessions.pop(request.cookies.get(COOKIE, ""), None)


def session_user(request: Request) -> User | None:
    """The signed-in user. A local user is checked against the users file on every request:
    a removed user or a changed password ends the session."""
    user, stamp, expires = _sessions.get(request.cookies.get(COOKIE, ""), (None, "", 0.0))
    if user is None or expires <= time.monotonic():
        return None
    if user.source != "local":
        return user
    stored = users.find(get_settings(), user.name)
    if stored is None or stored.password_hash != stamp:
        return None
    return User(name=stored.name, role=stored.role)


def _take_attempt(name: str) -> bool:
    """Counted before the check, so parallel guesses can't slip past the limit."""
    now = time.monotonic()
    with _lock:
        recent = [t for t in _failures.pop(name, []) if t > now - FAILURE_SECONDS]
        allowed = len(recent) < MAX_FAILURES
        if allowed:
            recent.append(now)
        while len(_failures) >= MAX_TRACKED_NAMES:
            del _failures[next(iter(_failures))]
        _failures[name] = recent
    return allowed


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# Not async: hashing a password takes a while and must not block other requests.
@router.post("/session")
def sign_in(body: Credentials, request: Request, response: Response) -> User:
    settings = get_settings()
    if not check_settings(settings):
        raise HTTPException(404, "login_off")
    name = users.normalize(body.name)
    if not _take_attempt(name):
        raise HTTPException(429, "too_many_attempts")
    user, token = _check_password(settings, name, body)
    with _lock:
        _failures.pop(name, None)
    _close_session(request)
    _set_cookie(response, token)
    return user


def _check_password(settings, name: str, body: Credentials) -> tuple[User, str]:
    """Local account first; with no local account of that name, LDAP when it is set up."""
    ldap = auth_settings.current("ldap")
    if users.find(settings, name) is not None or not ldap.enabled:
        stored = users.verify(settings, name, body.password)
        if stored is None:
            raise HTTPException(401, "wrong_credentials")
        return User(name=stored.name, role=stored.role), open_session(stored)
    try:
        found = ldap_auth.authenticate(ldap, body.name, body.password)
    except ldap_auth.NotAllowed:
        raise HTTPException(403, "not_allowed") from None
    except ldap_auth.LdapError as e:
        log.warning("auth: LDAP unavailable: %s", e.code)
        raise HTTPException(503, "directory_unavailable") from None
    if found is None:
        raise HTTPException(401, "wrong_credentials")
    user = User(
        name=found.name,
        role=found.role,
        display_name=found.display_name,
        email=found.email,
        source="ldap",
    )
    return user, open_external_session(user)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=get_settings().cookie_secure,
    )


@router.delete("/session", status_code=204)
def sign_out(request: Request, response: Response) -> None:
    _close_session(request)
    response.delete_cookie(
        COOKIE, httponly=True, samesite="strict", secure=get_settings().cookie_secure
    )


@router.get("/methods")
def methods() -> dict:
    """What the login page offers. Says only whether LDAP and SSO are on, nothing else."""
    if not check_settings(get_settings()):
        raise HTTPException(404, "login_off")
    cfg = auth_settings.current("sso")
    return {
        "local": True,
        "ldap": auth_settings.current("ldap").enabled,
        "sso": {"label": cfg.label or "SSO"} if cfg.enabled else None,
    }


def _redirect_uri(request: Request, cfg: auth_settings.SsoSettings) -> str:
    return cfg.redirect_url or str(request.url_for("sso_callback"))


def _back_to_app(error: str | None = None) -> RedirectResponse:
    res = RedirectResponse("/" + (f"?sso={error}" if error else ""), status_code=303)
    res.delete_cookie(SSO_COOKIE, path=SSO_PATH)
    return res


@router.get("/sso/start")
def sso_start(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not check_settings(settings):
        raise HTTPException(404, "login_off")
    cfg = auth_settings.current("sso")
    try:
        url, state = sso.start(cfg, _redirect_uri(request, cfg))
    except sso.SsoError as e:
        log.warning("auth: SSO unavailable: %s", e.code)
        return _back_to_app("unavailable")
    res = RedirectResponse(url, status_code=303)
    # Lax, not Strict: the identity provider sends the browser back here from another site
    res.set_cookie(
        SSO_COOKIE,
        state,
        max_age=sso.STATE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path=SSO_PATH,
    )
    return res


@router.get("/sso/callback", name="sso_callback")
def sso_callback(
    request: Request,
    code: str = Query("", max_length=4096),
    state: str = Query("", max_length=200),
    error: str = Query("", max_length=200),
) -> RedirectResponse:
    if not check_settings(get_settings()):
        raise HTTPException(404, "login_off")
    cookie = request.cookies.get(SSO_COOKIE, "")
    # the state must come back to the same browser that started: stops login CSRF
    if error or not code or not state or not secrets.compare_digest(cookie, state):
        return _back_to_app("failed")
    cfg = auth_settings.current("sso")
    try:
        found = sso.finish(cfg, code, state, _redirect_uri(request, cfg))
    except sso.NotAllowed:
        return _back_to_app("not_allowed")
    except sso.SsoError as e:
        log.warning("auth: SSO sign in failed: %s", e.code)
        return _back_to_app("failed")
    user = User(
        name=found.name,
        role=found.role,
        display_name=found.display_name,
        email=found.email,
        source="sso",
    )
    _close_session(request)
    res = _back_to_app()
    _set_cookie(res, open_external_session(user))
    log.info("auth: %s signed in with SSO as %s", user.name, user.role)
    return res


@router.get("/me")
def me(request: Request) -> User:
    if not check_settings(get_settings()):
        raise HTTPException(404, "login_off")
    user = session_user(request)
    if user is None:
        raise HTTPException(401, "unauthenticated")
    return user


def install(app: FastAPI) -> None:
    app.include_router(router)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        path = request.url.path
        guarded = path.startswith("/api/") and path.rstrip("/") not in OPEN_PATHS
        # session_user reads the users file, so it runs off the event loop
        if (
            guarded
            and check_settings(get_settings())
            and await run_in_threadpool(session_user, request) is None
        ):
            return JSONResponse({"detail": "unauthenticated"}, status_code=401)
        return await call_next(request)

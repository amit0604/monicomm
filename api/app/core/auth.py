"""Login with local users (core/users.py). No internet needed.

With MONICOMM_AUTH_PROVIDER=local every /api route except health and login needs a session.
"""

import secrets
import threading
import time

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core import users
from app.core.config import Settings, get_settings

COOKIE = "monicomm_session"
SESSION_SECONDS = 8 * 3600
MAX_SESSIONS = 1000
MAX_FAILURES = 5
FAILURE_SECONDS = 5 * 60
MAX_TRACKED_NAMES = 1000
OPEN_PATHS = ("/api/v1/health", "/api/v1/auth/session", "/api/v1/auth/me")


class User(BaseModel):
    name: str
    role: users.Role


class Credentials(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=users.MAX_PASSWORD)


# One api process; a restart signs everyone out.
# token -> user name, the password hash at sign in, expiry
_sessions: dict[str, tuple[str, str, float]] = {}
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def check_settings(settings: Settings) -> bool:
    """True when login is on. Raises on a configuration that must never start."""
    if settings.auth_provider == "none":
        return False
    if settings.auth_provider != "local":
        raise RuntimeError(f"Unknown MONICOMM_AUTH_PROVIDER {settings.auth_provider!r}")
    return True


def open_session(user: users.StoredUser) -> str:
    now = time.monotonic()
    token = secrets.token_urlsafe(32)
    with _lock:
        for old in [t for t, (_, _, expires) in _sessions.items() if expires <= now]:
            del _sessions[old]
        while len(_sessions) >= MAX_SESSIONS:
            del _sessions[next(iter(_sessions))]  # the oldest
        _sessions[token] = (user.name, user.password_hash, now + SESSION_SECONDS)
    return token


def _close_session(request: Request) -> None:
    with _lock:
        _sessions.pop(request.cookies.get(COOKIE, ""), None)


def session_user(request: Request) -> User | None:
    """The signed-in user as stored now: a removed user or a changed password ends the session."""
    name, password_hash, expires = _sessions.get(request.cookies.get(COOKIE, ""), ("", "", 0.0))
    if not name or expires <= time.monotonic():
        return None
    user = users.find(get_settings(), name)
    if user is None or user.password_hash != password_hash:
        return None
    return User(name=user.name, role=user.role)


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
    user = users.verify(settings, name, body.password)
    if user is None:
        raise HTTPException(401, "wrong_credentials")
    with _lock:
        _failures.pop(name, None)
    _close_session(request)
    response.set_cookie(
        COOKIE,
        open_session(user),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )
    return User(name=user.name, role=user.role)


@router.delete("/session", status_code=204)
def sign_out(request: Request, response: Response) -> None:
    _close_session(request)
    response.delete_cookie(
        COOKIE, httponly=True, samesite="strict", secure=get_settings().cookie_secure
    )


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

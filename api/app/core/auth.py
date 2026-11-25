"""DEV-ONLY login with Google Firebase (PROJECT.md decision log). Never runs on the closed network.

Firebase proves who the user is; this module decides who may enter and keeps the session. With
MONICOMM_AUTH_PROVIDER=firebase every /api route except health and login needs a session.
"""

import secrets
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core import admin_emails
from app.core.config import Settings, get_settings

LOOKUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"  # airgap: allow
COOKIE = "monicomm_session"
SESSION_SECONDS = 8 * 3600
MAX_SESSIONS = 1000
OPEN_PATHS = ("/api/v1/health", "/api/v1/auth/config", "/api/v1/auth/session")


class AuthUnavailable(RuntimeError):
    """Firebase can't be reached or answered with an error."""


class User(BaseModel):
    name: str
    role: Literal["admin"]


class AuthConfig(BaseModel):
    """Public Firebase web settings; the browser needs them to sign in."""

    api_key: str
    auth_domain: str
    project_id: str
    admin_login: str


class SessionRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=8192)


# token -> user, expiry, and the email that let them in ("" = by user id).
# One dev process; a restart signs everyone out.
_sessions: dict[str, tuple[User, float, str]] = {}


def check_settings(settings: Settings) -> bool:
    """True when login is on. Raises on a configuration that must never start."""
    if settings.auth_provider == "none":
        return False
    if settings.auth_provider != "firebase":
        raise RuntimeError(f"Unknown MONICOMM_AUTH_PROVIDER {settings.auth_provider!r}")
    if settings.env != "dev":
        raise RuntimeError("Firebase login is dev-only. Monicomm is air-gapped.")
    needed = (
        settings.firebase_api_key,
        settings.firebase_auth_domain,
        settings.firebase_project_id,
    )
    if not all(needed):
        raise RuntimeError(
            "Firebase login needs MONICOMM_FIREBASE_API_KEY, _AUTH_DOMAIN, _PROJECT_ID"
        )
    return True


def _list(value: str) -> set[str]:
    return {v.strip() for v in value.split(",") if v.strip()}


def _by_uid(account: dict[str, Any], settings: Settings) -> bool:
    return str(account.get("localId", "")) in _list(settings.admin_uids)


def allowed_user(account: dict[str, Any], settings: Settings) -> User | None:
    """Anyone can create a Firebase account, so only listed people get in.

    An email counts only when verified: otherwise a stranger could register an admin's address.
    """
    if account.get("disabled"):
        return None
    uid, email = str(account.get("localId", "")), str(account.get("email", "")).lower()
    by_email = account.get("emailVerified") is True and admin_emails.allowed(settings, email)
    if not (_by_uid(account, settings) or by_email):
        return None
    return User(name=account.get("displayName") or email or uid, role="admin")


async def lookup(id_token: str, api_key: str) -> dict[str, Any] | None:
    """Ask Firebase who this token belongs to. None = the token is not valid for our project."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                LOOKUP_URL, json={"idToken": id_token}, headers={"x-goog-api-key": api_key}
            )
        if res.status_code == 400:
            return None
        res.raise_for_status()
        users = res.json().get("users") or []
    except (httpx.HTTPError, ValueError, AttributeError) as e:
        raise AuthUnavailable(type(e).__name__) from e
    return users[0] if users else None


def open_session(user: User, email: str = "") -> str:
    now = time.monotonic()
    for token in [t for t, (_, expires, _) in _sessions.items() if expires <= now]:
        del _sessions[token]
    while len(_sessions) >= MAX_SESSIONS:
        del _sessions[next(iter(_sessions))]  # the oldest
    token = secrets.token_urlsafe(32)
    _sessions[token] = (user, now + SESSION_SECONDS, email)
    return token


def session_user(request: Request) -> User | None:
    user, expires, email = _sessions.get(request.cookies.get(COOKIE, ""), (None, 0.0, ""))
    if user is None or expires <= time.monotonic():
        return None
    if email and not admin_emails.allowed(get_settings(), email):
        return None  # removed from the list since signing in
    return user


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/config")
def config() -> AuthConfig:
    s = get_settings()
    if not check_settings(s):
        raise HTTPException(404, "login_off")
    return AuthConfig(
        api_key=s.firebase_api_key,
        auth_domain=s.firebase_auth_domain,
        project_id=s.firebase_project_id,
        admin_login=s.firebase_admin_login,
    )


@router.post("/session")
async def sign_in(body: SessionRequest, request: Request, response: Response) -> User:
    s = get_settings()
    if not check_settings(s):
        raise HTTPException(404, "login_off")
    try:
        account = await lookup(body.id_token, s.firebase_api_key)
    except AuthUnavailable:
        raise HTTPException(503, "auth_unavailable") from None
    if account is None:
        raise HTTPException(401, "invalid_token")
    user = allowed_user(account, s)
    if user is None:
        raise HTTPException(403, "not_allowed")
    _sessions.pop(request.cookies.get(COOKIE, ""), None)
    email = "" if _by_uid(account, s) else str(account.get("email", ""))
    response.set_cookie(
        COOKIE, open_session(user, email), max_age=SESSION_SECONDS, httponly=True, samesite="strict"
    )
    return user


@router.delete("/session", status_code=204)
def sign_out(request: Request, response: Response) -> None:
    _sessions.pop(request.cookies.get(COOKIE, ""), None)
    response.delete_cookie(COOKIE, httponly=True, samesite="strict")


@router.get("/me")
def me(request: Request) -> User:
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
        if guarded and check_settings(get_settings()) and session_user(request) is None:
            return JSONResponse({"detail": "unauthenticated"}, status_code=401)
        return await call_next(request)

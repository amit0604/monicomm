"""Admin page API: /api/v1/admin/llm, the Chat AI model connection. Signed-in admins only.

The API key is write-only: no reply ever contains it.
"""

import logging
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.ai import llm_client, llm_settings
from app.core import auth
from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)
MODEL_NAME = r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"  # ollama: "qwen2.5:7b", "library/name"
GEMINI_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"  # goes into a URL path


def require_admin(request: Request) -> auth.User:
    """Closed when login is off: without login anyone could change the key."""
    if not auth.check_settings(get_settings()):
        raise HTTPException(403, "login_off")
    user = auth.session_user(request)
    if user is None:
        raise HTTPException(401, "unauthenticated")
    if user.role != "admin":
        raise HTTPException(403, "admin_only")
    return user


AdminDep = Annotated[auth.User, Depends(require_admin)]


class LLMForm(BaseModel):
    provider: Literal["ollama", "gemini"]
    base_url: str = Field(min_length=1, max_length=300)
    model: str = Field(max_length=100, pattern=MODEL_NAME)
    gemini_model: str = Field(max_length=100, pattern=GEMINI_NAME)
    api_key: SecretStr | None = None  # None = keep the current key

    @field_validator("api_key")
    @classmethod
    def printable(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            key = value.get_secret_value()
            if not 0 < len(key) <= 500 or not all("!" <= c <= "~" for c in key):
                raise ValueError("invalid key")
        return value


class LLMView(BaseModel):
    provider: str
    base_url: str
    model: str
    gemini_model: str
    key_source: Literal["none", "env", "saved"]
    saved: bool  # False = everything comes from .env


class CheckResult(BaseModel):
    ok: bool
    error: (
        Literal["key_missing", "key_rejected", "model_not_found", "rate_limited", "unavailable"]
        | None
    ) = None


def _view() -> LLMView:
    saved = llm_settings.load(get_settings())
    now = llm_settings.current()
    key_source: Literal["none", "env", "saved"] = "env" if now.gemini_api_key else "none"
    if saved and saved.gemini_api_key:
        key_source = "saved"
    return LLMView(
        provider=now.llm_provider,
        base_url=now.llm_base_url,
        model=now.llm_model,
        gemini_model=now.gemini_model,
        key_source=key_source,
        saved=saved is not None,
    )


def _from_form(form: LLMForm) -> tuple[Settings, llm_settings.SavedLLM]:
    settings = get_settings()
    try:
        base_url = llm_client.validate_llm_url(form.base_url.strip()).rstrip("/")
    except ValueError:  # ExternalEndpointError, or a URL that can't be parsed
        raise HTTPException(400, "external_url") from None
    before = llm_settings.load(settings)
    key = form.api_key.get_secret_value() if form.api_key else ""
    saved = llm_settings.SavedLLM(
        llm_provider=form.provider,
        llm_base_url=base_url,
        llm_model=form.model,
        gemini_model=form.gemini_model,
        gemini_api_key=key or (before.gemini_api_key if before else ""),
    )
    return settings, saved


def _explain(error: llm_client.LLMUnavailable) -> CheckResult:
    cause = error.__cause__
    status = cause.response.status_code if isinstance(cause, httpx.HTTPStatusError) else 0
    if status in (400, 401, 403):  # Gemini answers 400 to an invalid key
        return CheckResult(ok=False, error="key_rejected")
    if status == 404:
        return CheckResult(ok=False, error="model_not_found")
    if status == 429:
        return CheckResult(ok=False, error="rate_limited")
    return CheckResult(ok=False, error="unavailable")


router = APIRouter(prefix="/api/v1/admin/llm", tags=["admin"])


@router.get("")
def read(_admin: AdminDep) -> LLMView:
    return _view()


@router.put("")
def write(form: LLMForm, admin: AdminDep) -> LLMView:
    settings, saved = _from_form(form)
    if form.provider == "gemini" and not llm_settings.merge(settings, saved).gemini_api_key:
        raise HTTPException(400, "key_missing")
    try:
        llm_settings.save(settings, saved)
    except OSError as e:
        log.error("admin: can't save the model connection: %s", type(e).__name__)
        raise HTTPException(500, "save_failed") from None
    log.info("admin: %s set the model connection to %s", admin.name, form.provider)
    return _view()


@router.delete("")
def reset(admin: AdminDep) -> LLMView:
    llm_settings.reset(get_settings())
    log.info("admin: %s reset the model connection to .env", admin.name)
    return _view()


@router.post("/test")
async def check(form: LLMForm, _admin: AdminDep) -> CheckResult:
    """Send one fixed message to the model with these values, without saving them."""
    settings, saved = _from_form(form)
    merged = llm_settings.merge(settings, saved)
    if form.provider == "gemini" and not merged.gemini_api_key:
        return CheckResult(ok=False, error="key_missing")
    try:
        await llm_client.chat([{"role": "user", "content": "Reply with: ok"}], merged)
    except llm_client.LLMUnavailable as e:
        return _explain(e)
    return CheckResult(ok=True)

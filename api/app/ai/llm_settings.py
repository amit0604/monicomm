"""The model connection: .env values, plus what an admin saved on the Admin page.

DEV-ONLY (PROJECT.md decision log): the saved values, including the API key, are in a local
git-ignored file that is not encrypted, like .env. The file is ignored unless MONICOMM_ENV=dev and
login is on.
"""

import os
from pathlib import Path

from pydantic import BaseModel

from app.core.config import Settings, get_settings


class SavedLLM(BaseModel):
    """Field names match Settings."""

    llm_provider: str
    llm_base_url: str
    llm_model: str
    gemini_model: str
    gemini_api_key: str = ""  # empty = the one from .env


def enabled(settings: Settings) -> bool:
    return settings.env == "dev" and settings.auth_provider != "none"


def load(settings: Settings) -> SavedLLM | None:
    if not enabled(settings):
        return None
    try:
        return SavedLLM.model_validate_json(Path(settings.llm_settings_file).read_text("utf-8"))
    except (OSError, ValueError):
        return None  # missing or damaged: .env applies


def save(settings: Settings, saved: SavedLLM) -> None:
    path = Path(settings.llm_settings_file)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(saved.model_dump_json())
    os.replace(tmp, path)  # a reader never sees half a file


def reset(settings: Settings) -> None:
    Path(settings.llm_settings_file).unlink(missing_ok=True)


def merge(settings: Settings, saved: SavedLLM) -> Settings:
    update = saved.model_dump()
    if not saved.gemini_api_key:
        del update["gemini_api_key"]
    return settings.model_copy(update=update)


def current() -> Settings:
    """The settings every model call uses."""
    settings = get_settings()
    saved = load(settings)
    return merge(settings, saved) if saved else settings

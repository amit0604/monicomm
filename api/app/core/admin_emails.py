"""Who may enter by verified email: MONICOMM_ADMIN_EMAILS, plus those added on the Admin page.

DEV-ONLY, like the login itself. The added addresses are in a local git-ignored file. A missing or
damaged file adds nobody.
"""

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.core.config import Settings

MAX_EMAILS = 50
EMAIL = re.compile(r"[!-~]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


class EmailList(BaseModel):
    emails: list[str] = Field(max_length=MAX_EMAILS)

    @field_validator("emails")
    @classmethod
    def normalized(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip().lower() for v in values]
        for v in cleaned:
            if len(v) > 254 or "," in v or v.count("@") != 1 or not EMAIL.fullmatch(v):
                raise ValueError("invalid email")
        return list(dict.fromkeys(cleaned))


def from_env(settings: Settings) -> list[str]:
    return [e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()]


def load(settings: Settings) -> list[str]:
    try:
        text = Path(settings.admin_emails_file).read_text("utf-8")
        return EmailList.model_validate_json(text).emails
    except (OSError, ValueError):
        return []


def save(settings: Settings, emails: EmailList) -> None:
    path = Path(settings.admin_emails_file)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(emails.model_dump_json())
    os.replace(tmp, path)  # a reader never sees half a file


def allowed(settings: Settings, email: str) -> bool:
    email = email.lower()
    return bool(email) and (email in from_env(settings) or email in load(settings))

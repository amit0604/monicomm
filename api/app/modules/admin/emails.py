"""Admin page API: /api/v1/admin/emails, who may sign in as an admin. Signed-in admins only."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import admin_emails
from app.core.config import get_settings
from app.modules.admin.router import AdminDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/emails", tags=["admin"])


class EmailsView(BaseModel):
    env: list[str]  # from .env, can't be changed here
    saved: list[str]


def _view() -> EmailsView:
    settings = get_settings()
    return EmailsView(env=admin_emails.from_env(settings), saved=admin_emails.load(settings))


@router.get("")
def read(_admin: AdminDep) -> EmailsView:
    return _view()


@router.put("")
def write(form: admin_emails.EmailList, admin: AdminDep) -> EmailsView:
    """Replace the saved list. Someone removed from it loses access at once."""
    try:
        admin_emails.save(get_settings(), form)
    except OSError as e:
        log.error("admin: can't save the admin emails: %s", type(e).__name__)
        raise HTTPException(500, "save_failed") from None
    log.info("admin: %s changed the admin emails (%d now)", admin.name, len(form.emails))
    return _view()

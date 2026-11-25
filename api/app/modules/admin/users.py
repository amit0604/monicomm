"""Admin page API: /api/v1/admin/users. Signed-in admins only. Hashes never leave the server."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import users
from app.core.config import get_settings
from app.modules.admin.router import AdminDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])
STATUS = {"not_found": 404, "exists": 409, "last_admin": 409, "too_many": 409}


class UserView(BaseModel):
    name: str
    role: users.Role


def _refused(error: users.UsersError) -> HTTPException:
    status = STATUS.get(error.code, 500)
    if status == 500:
        log.error("admin: users file: %s", error.code)
    return HTTPException(status, error.code)


def _view() -> list[UserView]:
    return [UserView(name=u.name, role=u.role) for u in users.load(get_settings())]


@router.get("")
def read(_admin: AdminDep) -> list[UserView]:
    try:
        return _view()
    except users.UsersError as e:
        raise _refused(e) from None


@router.post("")
def add(new: users.NewUser, admin: AdminDep) -> list[UserView]:
    try:
        users.add(get_settings(), new)
        log.info("admin: %s added user %s (%s)", admin.name, new.name, new.role)
        return _view()
    except users.UsersError as e:
        raise _refused(e) from None


@router.delete("/{name}")
def remove(name: str, admin: AdminDep) -> list[UserView]:
    """The removed user is signed out at once. The last admin can't be removed."""
    try:
        users.remove(get_settings(), name)
        log.info("admin: %s removed user %s", admin.name, name)
        return _view()
    except users.UsersError as e:
        raise _refused(e) from None


@router.put("/{name}/password", status_code=204)
def set_password(name: str, new: users.NewPassword, admin: AdminDep) -> None:
    """Signs the user out everywhere."""
    try:
        users.set_password(get_settings(), name, new)
        log.info("admin: %s set the password of %s", admin.name, name)
    except users.UsersError as e:
        raise _refused(e) from None

"""DEV-ONLY: create the first Firebase admin user and print the line to add to .env.

    cd api; uv run --env-file ../.env python -m scripts.create_dev_admin

The password is typed in, never stored. Firebase requires at least 6 characters.
"""

import getpass
import sys

import httpx

from app.core.auth import check_settings
from app.core.config import get_settings

SIGN_UP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"  # airgap: allow


def main() -> int:
    settings = get_settings()
    if not check_settings(settings):
        print("Set MONICOMM_AUTH_PROVIDER=firebase first.")
        return 1
    email = settings.firebase_admin_login
    password = getpass.getpass(f"Password for {email}: ")
    if len(password) < 6 or password != getpass.getpass("Again: "):
        print("The passwords differ or are shorter than 6 characters.")
        return 1
    res = httpx.post(
        SIGN_UP_URL,
        json={"email": email, "password": password, "returnSecureToken": True},
        headers={"x-goog-api-key": settings.firebase_api_key},
        timeout=20,
    )
    body = res.json()
    if res.status_code != 200:
        print("Firebase refused:", body.get("error", {}).get("message", res.status_code))
        return 1
    print(f"Created. Add this to .env and restart the api:\nMONICOMM_ADMIN_UIDS={body['localId']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

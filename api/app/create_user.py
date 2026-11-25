"""Create a local user, for the first admin.

    cd api; uv run --env-file ../.env python -m app.create_user admin
    docker compose exec api python -m app.create_user admin

The password is typed in and only its hash is stored.
"""

import getpass
import sys

from pydantic import ValidationError

from app.core import users
from app.core.config import get_settings


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print("Usage: python -m app.create_user NAME [admin|technician|viewer]")
        return 2
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Again: "):
        print("The passwords differ.")
        return 1
    try:
        role = argv[1] if len(argv) == 2 else "admin"
        new = users.NewUser(name=argv[0], role=role, password=password)
        users.add(get_settings(), new)
    except ValidationError as e:
        print("Not valid:", ", ".join(str(x["loc"][0]) for x in e.errors()))
        return 1
    except users.UsersError as e:
        print("Failed:", e.code)
        return 1
    print(f"Created {new.name} ({new.role}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

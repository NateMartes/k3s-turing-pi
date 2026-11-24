#!/usr/bin/env python3
import argparse

from lib.platform_common import get_user, require_root
from lib.user_privileges import PRIVILEGES, grant_privilege, validate_username


def main():
    parser = argparse.ArgumentParser(
        description="Grant an allowlisted elevated privilege to a managed user."
    )
    parser.add_argument("username", metavar="USERNAME")
    parser.add_argument(
        "privilege",
        choices=sorted(PRIVILEGES),
        metavar="PRIVILEGE",
        help="Supported: " + ", ".join(sorted(PRIVILEGES)),
    )
    args = parser.parse_args()

    require_root()
    username = validate_username(args.username)
    get_user(username)
    definition = grant_privilege(username, args.privilege)

    print(f"Granted {definition.token} to {username}.")
    print(f"The user can now {definition.description}.")


if __name__ == "__main__":
    main()

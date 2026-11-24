#!/usr/bin/env python3
import argparse

from lib.platform_common import require_root
from lib.user_privileges import PRIVILEGES, revoke_privilege


def main():
    parser = argparse.ArgumentParser(
        description="Revoke an allowlisted elevated privilege from a managed user."
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
    definition = revoke_privilege(args.username, args.privilege)

    print(f"Revoked {definition.token} from {args.username}.")
    print("Shared roles and the user's normal read-only access were preserved.")


if __name__ == "__main__":
    main()

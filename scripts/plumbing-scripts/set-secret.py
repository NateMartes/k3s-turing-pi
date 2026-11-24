#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.jihwija_common import JihwijaError, parse_env, require_root, secure_value, write_env


KEYS = {
    "RANCHER_BOOTSTRAP_PASSWORD",
    "RANCHER_TOKEN",
    "HARBOR_ADMIN_PASSWORD",
    "PORTAINER_API_KEY",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Store a protected Jihwija service secret.")
    parser.add_argument("key", choices=sorted(KEYS))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--value-file", type=Path)
    source.add_argument("--stdin", action="store_true")
    args = parser.parse_args()
    require_root()
    try:
        if args.value_file:
            value = args.value_file.read_text().rstrip("\r\n")
        elif args.stdin:
            value = sys.stdin.read().rstrip("\r\n")
        else:
            value = secure_value(args.key)
        if not value or "\n" in value or "\r" in value:
            raise JihwijaError("Secret must be non-empty and contain no newlines.")
        values = parse_env()
        values[args.key] = value
        write_env(values)
        print(f"Stored {args.key}.")
    except (JihwijaError, OSError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()

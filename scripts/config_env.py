#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path


SYSADMIN_ENV = Path("/etc/k3s-turing-pi/sysadmin-env")
VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ConfigError(RuntimeError):
    pass


def load_sysadmin_env(path: Path = SYSADMIN_ENV) -> None:
    """Load simple shell-style assignments without executing the file."""
    if not path.exists():
        return

    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        try:
            fields = shlex.split(stripped, comments=True, posix=True)
        except ValueError as exc:
            raise ConfigError(f"{path}:{line_number}: {exc}") from exc

        if fields and fields[0] == "export":
            fields = fields[1:]
        if not fields:
            continue
        if len(fields) != 1 or "=" not in fields[0]:
            raise ConfigError(
                f"{path}:{line_number}: expected 'NAME=value' or 'export NAME=value'."
            )

        name, value = fields[0].split("=", 1)
        if not VARIABLE_NAME.fullmatch(name):
            raise ConfigError(f"{path}:{line_number}: invalid variable name {name!r}.")

        # An explicitly supplied environment variable takes precedence.
        os.environ.setdefault(name, value)


def load_sysadmin_env_or_exit(path: Path = SYSADMIN_ENV) -> None:
    try:
        load_sysadmin_env(path)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

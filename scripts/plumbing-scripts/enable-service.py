#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from lib.jihwija_common import JihwijaError, require_root, run_plumbing
from lib.service_management import SERVICE_MANIFESTS, set_service_enabled


def main() -> None:
    parser = argparse.ArgumentParser(description="Enable and deploy a Jihwija service.")
    parser.add_argument("service", choices=sorted(SERVICE_MANIFESTS))
    args = parser.parse_args()
    require_root()

    try:
        changed = set_service_enabled(args.service, True)
        run_plumbing("deploy-services.py", "--service", args.service)
        state = "Enabled" if changed else "Already enabled"
        print(f"{state}: {args.service}")
    except (JihwijaError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()

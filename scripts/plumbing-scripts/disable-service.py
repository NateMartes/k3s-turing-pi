#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from lib.jihwija_common import JihwijaError, kubectl, require_root, run_plumbing
from lib.service_management import CHART_NAMES, SERVICE_MANIFESTS, set_service_enabled


def main() -> None:
    parser = argparse.ArgumentParser(description="Disable and remove a Jihwija service.")
    parser.add_argument("service", choices=sorted(SERVICE_MANIFESTS))
    args = parser.parse_args()
    require_root()

    try:
        changed = set_service_enabled(args.service, False)
        kubectl(
            "delete",
            "helmchart",
            CHART_NAMES[args.service],
            "-n",
            "kube-system",
            "--ignore-not-found",
        )
        run_plumbing("deploy-services.py")
        state = "Disabled" if changed else "Already disabled"
        print(f"{state}: {args.service}")
    except (JihwijaError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()

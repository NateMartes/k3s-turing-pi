#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from lib.jihwija_common import (
    JihwijaError,
    PLUMBING_DIR,
    kubectl,
    parse_env,
    prompt,
    prompt_bool,
    require_root,
    validate_hostname,
    write_env,
    atomic_write,
)


VARIABLES = {
    "rancher": "RANCHER_HOSTNAME",
    "harbor": "HARBOR_HOSTNAME",
    "portainer": "PORTAINER_HOSTNAME",
    "argo": "ARGO_HOSTNAME",
    "grafana": "GRAFANA_HOSTNAME",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a Jihwija service hostname.")
    parser.add_argument("service", choices=sorted(VARIABLES))
    parser.add_argument("hostname", nargs="?")
    parser.add_argument("--redeploy", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    require_root()
    try:
        hostname = validate_hostname(args.hostname or prompt(f"{args.service.title()} hostname"))
        values = parse_env()
        values[VARIABLES[args.service]] = hostname
        write_env(values)
        if args.service == "argo":
            project_root = Path(__file__).resolve().parents[2]
            template = project_root / "etc" / "profile.d" / "jihwija-argo-variables.sh"
            profile = template.read_text()
            profile = profile.replace("@ARGO_HOSTNAME@", hostname)
            # Reconfiguration replaces the previously rendered hostname too.
            profile = re.sub(
                r'export ARGO_SERVER="[^"]+:443"',
                f'export ARGO_SERVER="{hostname}:443"',
                profile,
                count=1,
            )
            destination = Path("/etc/profile.d/jihwija-argo-variables.sh")
            atomic_write(destination, profile, 0o644)

        try:
            deployed = kubectl(
                "get", "helmchart", args.service if args.service != "argo" else "argo-workflows",
                "-n", "kube-system", "--ignore-not-found", "-o", "name",
                capture=True, check=False,
            ).stdout.strip()
        except JihwijaError:
            deployed = ""
        redeploy = args.redeploy
        if deployed and redeploy is None:
            redeploy = prompt_bool("Service is already deployed; redeploy it?", False)
        if deployed and redeploy:
            subprocess.run(
                [str(PLUMBING_DIR / "deploy-services.py"), "--service", args.service],
                check=True,
            )
        elif not deployed:
            print("Hostname saved; it will take effect during `jihwija deploy`.")
        print(f"{args.service.title()}: https://{hostname}")
    except (JihwijaError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()

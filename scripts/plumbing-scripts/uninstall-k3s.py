#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from lib.jihwija_common import (
    INVENTORY_PATH,
    JihwijaError,
    inventory_hosts,
    load_yaml,
    prompt_bool,
    require_root,
    run_ansible_playbook,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove K3s, cluster state, local K3s storage, CNI state, and "
            "residual K3s networking from every inventory node."
        )
    )
    parser.add_argument("--yes", action="store_true", help="Skip destructive confirmation.")
    args = parser.parse_args()
    require_root()
    try:
        if not INVENTORY_PATH.exists():
            raise JihwijaError("Run `jihwija init INVENTORY` first.")
        inventory = load_yaml(INVENTORY_PATH)
        hosts = inventory_hosts(inventory)
        if not hosts:
            raise JihwijaError("The inventory contains no hosts.")

        print("K3s full-cluster uninstall")
        print("--------------------------")
        print(f"Nodes: {', '.join(sorted(hosts))}")
        print("Removes: K3s server and agents, cluster state, local K3s storage, CNI state, and residual networking")
        print("Preserves: Jihwija inventory, settings, secrets, and managed-user state")
        if not args.yes and not prompt_bool("Uninstall K3s from every listed node?", False):
            print("Cancelled.")
            return

        run_ansible_playbook("remove-k3s.yml")
        print("K3s was removed from every inventory node.")
        print("Run `sudo jihwija install k3s` to build the cluster again.")
    except (JihwijaError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: K3s uninstall failed: {exc}") from exc


if __name__ == "__main__":
    main()

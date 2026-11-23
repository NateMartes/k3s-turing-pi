#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from lib.jihwija_common import (
    INVENTORY_PATH,
    JihwijaError,
    inventory_hosts,
    kubectl,
    load_yaml,
    prompt_bool,
    remove_host,
    require_root,
    run_ansible_playbook,
    write_yaml,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Drain and remove a K3s worker node.")
    parser.add_argument("hostname")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument(
        "--delete-emptydir-data",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Permit deletion of temporary emptyDir Pod data while draining.",
    )
    parser.add_argument("--drain-timeout", default="10m")
    args = parser.parse_args()
    require_root()
    try:
        inventory = load_yaml(INVENTORY_PATH)
        hosts = inventory_hosts(inventory)
        variables = hosts.get(args.hostname)
        if variables is None:
            # A prior run may already have completed the inventory step.
            result = kubectl("get", "node", args.hostname, capture=True, check=False)
            if result.returncode != 0:
                print(f"Node {args.hostname} is already absent from the cluster and inventory.")
                return
            raise JihwijaError(f"Node {args.hostname!r} is not in the inventory.")
        protected = []
        if variables.get("k3s_host"):
            protected.append("K3s server")
        if variables.get("is_default_gateway"):
            protected.append("default gateway")
        if variables.get("is_jihwija_service_node"):
            protected.append("Jihwija service node")
        if protected:
            raise JihwijaError(
                f"Refusing to remove protected node {args.hostname}: {', '.join(protected)}."
            )
        print(f"Node:       {args.hostname}")
        print(f"Address:    {variables.get('ansible_host')}")
        print("Action:     cordon, drain, uninstall K3s agent, delete node, remove inventory entry")
        if not args.yes and not prompt_bool("Continue?", False):
            print("Cancelled.")
            return
        if args.delete_emptydir_data is None:
            args.delete_emptydir_data = prompt_bool(
                "Permit deletion of temporary emptyDir Pod data if needed?", False
            )

        exists = kubectl("get", "node", args.hostname, capture=True, check=False).returncode == 0
        if exists:
            kubectl("cordon", args.hostname)
            drain = [
                "drain", args.hostname, "--ignore-daemonsets", f"--timeout={args.drain_timeout}"
            ]
            if args.delete_emptydir_data:
                drain.append("--delete-emptydir-data")
            kubectl(*drain)

        # The playbook is idempotent and tolerates an agent that was already uninstalled.
        run_ansible_playbook("remove-k3s-node.yml", ["--limit", args.hostname])
        kubectl("delete", "node", args.hostname, "--ignore-not-found")
        remove_host(inventory, args.hostname)
        backup = write_yaml(INVENTORY_PATH, inventory)
        print(f"Removed worker node {args.hostname}.")
        if backup:
            print(f"Previous inventory: {backup}")
        kubectl("get", "nodes", "-o", "wide")
    except (JihwijaError, subprocess.CalledProcessError, OSError) as exc:
        raise SystemExit(
            f"ERROR: {exc}\nThe inventory entry was retained unless all removal stages completed. "
            "Rerun the command to resume safely."
        ) from exc


if __name__ == "__main__":
    main()

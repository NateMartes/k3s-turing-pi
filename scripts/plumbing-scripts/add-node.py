#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import subprocess

from lib.jihwija_common import (
    GROUP_VARS_PATH,
    INVENTORY_PATH,
    JihwijaError,
    add_host,
    group_for_host,
    inventory_groups,
    inventory_hosts,
    load_yaml,
    preflight_host,
    prompt,
    prompt_bool,
    remove_host,
    require_root,
    run_ansible_playbook,
    run_plumbing,
    validate_networks,
    write_yaml,
    kubectl,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Add and provision a K3s worker node.")
    parser.add_argument("hostname")
    parser.add_argument("ip_address")
    parser.add_argument("--group")
    parser.add_argument("--ansible-user")
    parser.add_argument("--service-node", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--desktop-node", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--flannel-interface")
    parser.add_argument("--dhcp-interface")
    parser.add_argument("--dhcp-definition")
    args = parser.parse_args()
    require_root()
    try:
        inventory = load_yaml(INVENTORY_PATH)
        settings = load_yaml(GROUP_VARS_PATH)
        hosts = inventory_hosts(inventory)
        address = str(ipaddress.ip_address(args.ip_address))
        lan = ipaddress.ip_network(settings["k3s_lan_cidr"], strict=False)
        if ipaddress.ip_address(address) not in lan:
            raise JihwijaError(f"Address {address} is outside the configured LAN {lan}.")
        existing = hosts.get(args.hostname)
        if existing and str(existing.get("ansible_host")) != address:
            raise JihwijaError(f"Host {args.hostname!r} already uses {existing.get('ansible_host')}.")
        for name, variables in hosts.items():
            if name != args.hostname and str(variables.get("ansible_host")) == address:
                raise JihwijaError(f"Address {address} is already used by {name!r}.")

        default_group = group_for_host(inventory, args.hostname)
        choices = ", ".join(sorted(name for name in inventory_groups(inventory) if name != "all"))
        group = args.group or prompt(f"Inventory group ({choices}; new names allowed)", default_group or "nodes")
        global_user = inventory.get("all", {}).get("vars", {}).get("ansible_user", "")
        user = args.ansible_user or prompt("SSH user", str((existing or {}).get("ansible_user", global_user)))
        service_node = args.service_node
        if service_node is None:
            service_node = prompt_bool("Use this worker for Jihwija services?", bool((existing or {}).get("is_jihwija_service_node")))
        desktop_node = args.desktop_node
        if desktop_node is None:
            desktop_node = prompt_bool("Is this a desktop node?", bool((existing or {}).get("is_desktop_node")))
        flannel = args.flannel_interface if args.flannel_interface is not None else prompt(
            "Flannel interface (blank for automatic)", str((existing or {}).get("k3s_flannel_iface", ""))
        )
        dhcp_interface = args.dhcp_interface if args.dhcp_interface is not None else prompt(
            "DHCP interface (blank for automatic)", str((existing or {}).get("netplan_dhcp_interface", ""))
        )
        dhcp_definition = args.dhcp_definition if args.dhcp_definition is not None else prompt(
            "Netplan definition (blank for automatic)", str((existing or {}).get("netplan_dhcp_definition", ""))
        )

        preflight_host(address, user, require_amd64=bool(service_node))
        variables = dict(existing or {})
        variables.update(ansible_host=address, ansible_user=user)
        for key, value in {
            "is_jihwija_service_node": service_node,
            "is_desktop_node": desktop_node,
            "k3s_flannel_iface": flannel,
            "netplan_dhcp_interface": dhcp_interface,
            "netplan_dhcp_definition": dhcp_definition,
        }.items():
            if value not in (False, "", None):
                variables[key] = value
            else:
                variables.pop(key, None)
        if existing:
            remove_host(inventory, args.hostname)
        add_host(inventory, group, args.hostname, variables)
        validate_networks(settings, inventory_hosts(inventory))
        backup = write_yaml(INVENTORY_PATH, inventory)
        print(f"Saved worker {args.hostname} ({address}) in group {group}.")
        if backup:
            print(f"Previous inventory: {backup}")
        try:
            run_ansible_playbook("setup-k3s.yml")
            # Reconcile GPU discovery and taints as part of every worker join.
            run_plumbing("deploy-services.py", "--service", "nvidia", "--timeout", "10m")
        except subprocess.CalledProcessError as exc:
            raise JihwijaError(
                "K3s provisioning failed; the inventory entry was retained as desired state. "
                "Rerun this command or `jihwija install k3s`."
            ) from exc
        kubectl("get", "nodes", "-o", "wide")
    except (JihwijaError, ValueError, OSError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()

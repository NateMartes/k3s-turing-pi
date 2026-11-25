#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
from pathlib import Path

from lib.jihwija_common import (
    GROUP_VARS_PATH,
    INVENTORY_PATH,
    JihwijaError,
    inventory_all,
    inventory_hosts,
    load_yaml,
    prompt,
    preflight_host,
    require_root,
    validate_networks,
    write_yaml,
)


DEFAULTS = {
    "k3s_version": "v1.36.1+k3s1",
    "k3s_lan_cidr": "10.42.0.0/24",
    "k3s_cluster_cidr": "10.244.0.0/16",
    "k3s_service_cidr": "10.43.0.0/16",
    "k3s_resolv_conf": "/etc/rancher/k3s/resolv.conf",
    "k3s_dns_servers": ["1.1.1.1", "8.8.8.8"],
    "k3s_flannel_iface": "",
    "k3s_snapshotter": "",
    "netplan_dhcp_apply": False,
    "netplan_dhcp_interface": "",
    "netplan_dhcp_definition": "",
    "default_gateway_lan_interface": "",
    "default_gateway_wan_interface": "",
}


def configuration_defaults(
    existing_settings: dict,
    inventory_variables: dict,
) -> dict:
    """Merge defaults in increasing order of relevance."""
    return {**DEFAULTS, **existing_settings, **inventory_variables}


def csv_prompt(label: str, default: list[str] | None = None) -> list[str]:
    text = prompt(label, ",".join(default or []))
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize Jihwija from an Ansible YAML inventory.")
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--ansible-user")
    parser.add_argument("--k3s-version")
    parser.add_argument("--lan-cidr")
    parser.add_argument("--pod-cidr")
    parser.add_argument("--service-cidr")
    parser.add_argument("--dns-server", action="append", dest="dns_servers")
    parser.add_argument("--resolv-conf")
    parser.add_argument("--flannel-interface")
    parser.add_argument("--snapshotter")
    parser.add_argument("--dhcp-apply", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--dhcp-interface")
    parser.add_argument("--dhcp-definition")
    parser.add_argument("--k3s-server")
    parser.add_argument("--service-node", action="append", dest="service_nodes")
    desktops = parser.add_mutually_exclusive_group()
    desktops.add_argument("--desktop-node", action="append", dest="desktop_nodes")
    desktops.add_argument("--no-desktop-nodes", action="store_true")
    gateway = parser.add_mutually_exclusive_group()
    gateway.add_argument("--gateway-node")
    gateway.add_argument("--no-gateway", action="store_true")
    parser.add_argument("--gateway-lan-interface")
    parser.add_argument("--gateway-wan-interface")
    parser.add_argument("--node-flannel", action="append", default=[], metavar="HOST=INTERFACE")
    parser.add_argument("--node-dhcp-interface", action="append", default=[], metavar="HOST=INTERFACE")
    parser.add_argument("--node-dhcp-definition", action="append", default=[], metavar="HOST=DEFINITION")
    return parser.parse_args()


def assignments(values: list[str], option: str) -> dict[str, str]:
    result = {}
    for value in values:
        hostname, separator, setting = value.partition("=")
        if not separator or not hostname:
            raise JihwijaError(f"{option} expects HOST=VALUE, got {value!r}.")
        result[hostname] = setting
    return result


def main() -> None:
    args = parse_args()
    require_root()
    try:
        inventory = load_yaml(args.inventory)
        hosts = inventory_hosts(inventory)
        if not hosts:
            raise JihwijaError("The inventory contains no hosts.")

        all_vars = inventory_all(inventory).setdefault("vars", {})
        existing_settings = load_yaml(GROUP_VARS_PATH) if GROUP_VARS_PATH.exists() else {}
        # An explicitly supplied inventory is the most relevant source of
        # defaults.  The normalized values are moved to group_vars below so
        # Ansible does not retain a stale, higher-precedence duplicate.
        defaults = configuration_defaults(existing_settings, all_vars)
        current_user = all_vars.get("ansible_user") or os.environ.get("SUDO_USER") or getpass.getuser()

        ansible_user = args.ansible_user or prompt("Default SSH user", str(current_user))
        k3s_version = args.k3s_version or prompt(
            "K3s version", str(all_vars.get("k3s_version", defaults["k3s_version"]))
        )
        lan = args.lan_cidr or prompt("LAN CIDR", str(defaults["k3s_lan_cidr"]))
        pods = args.pod_cidr or prompt("Pod CIDR", str(defaults["k3s_cluster_cidr"]))
        services = args.service_cidr or prompt(
            "Service CIDR", str(defaults["k3s_service_cidr"])
        )
        dns = args.dns_servers or csv_prompt(
            "Upstream DNS servers", list(defaults["k3s_dns_servers"])
        )
        resolv = args.resolv_conf or prompt(
            "K3s resolver path", str(defaults["k3s_resolv_conf"])
        )
        flannel = (
            args.flannel_interface
            if args.flannel_interface is not None
            else prompt("Default Flannel interface (blank for automatic)", str(defaults["k3s_flannel_iface"]))
        )
        snapshotter = (
            args.snapshotter
            if args.snapshotter is not None
            else str(defaults["k3s_snapshotter"])
        )
        dhcp_apply = args.dhcp_apply
        if dhcp_apply is None:
            answer = prompt("Apply DHCP changes immediately (true/false)", str(defaults["netplan_dhcp_apply"]).lower())
            dhcp_apply = answer.lower() in {"true", "yes", "y", "1"}
        dhcp_interface = args.dhcp_interface if args.dhcp_interface is not None else prompt(
            "Default DHCP interface (blank for automatic)", str(defaults["netplan_dhcp_interface"])
        )
        dhcp_definition = args.dhcp_definition if args.dhcp_definition is not None else prompt(
            "Default Netplan definition (blank for automatic)", str(defaults["netplan_dhcp_definition"])
        )

        names = sorted(hosts)
        current_server = next((n for n, v in hosts.items() if v.get("k3s_host")), None)
        server = args.k3s_server or prompt("K3s server node", current_server or names[0])
        current_services = [n for n, v in hosts.items() if v.get("is_jihwija_service_node")]
        service_nodes = args.service_nodes or csv_prompt(
            "Jihwija service nodes", current_services or [server]
        )
        current_desktops = [n for n, v in hosts.items() if v.get("is_desktop_node")]
        desktop_nodes = [] if args.no_desktop_nodes else args.desktop_nodes
        if desktop_nodes is None:
            desktop_nodes = csv_prompt("Desktop nodes (comma-separated, blank for none)", current_desktops)
        if args.no_gateway:
            gateway_node = None
        elif args.gateway_node:
            gateway_node = args.gateway_node
        else:
            current_gateway = next((n for n, v in hosts.items() if v.get("is_default_gateway")), "")
            gateway_node = prompt("Default gateway node (blank for none)", current_gateway) or None

        selected = [server, *service_nodes, *desktop_nodes]
        if gateway_node:
            selected.append(gateway_node)
        unknown = sorted(set(selected) - set(hosts))
        if unknown:
            raise JihwijaError(f"Unknown selected host(s): {', '.join(unknown)}")
        if not service_nodes:
            raise JihwijaError("At least one Jihwija service node is required.")

        for name, variables in hosts.items():
            for key in ("k3s_host", "is_default_gateway", "is_jihwija_service_node", "is_desktop_node"):
                variables.pop(key, None)
            if name == server:
                variables["k3s_host"] = True
            if name == gateway_node:
                variables["is_default_gateway"] = True
            if name in service_nodes:
                variables["is_jihwija_service_node"] = True
            if name in desktop_nodes:
                variables["is_desktop_node"] = True

        node_flannel = assignments(args.node_flannel, "--node-flannel")
        node_dhcp_interfaces = assignments(args.node_dhcp_interface, "--node-dhcp-interface")
        node_dhcp_definitions = assignments(args.node_dhcp_definition, "--node-dhcp-definition")
        override_hosts = set(node_flannel) | set(node_dhcp_interfaces) | set(node_dhcp_definitions)
        unknown_overrides = sorted(override_hosts - set(hosts))
        if unknown_overrides:
            raise JihwijaError(f"Node override refers to unknown host(s): {', '.join(unknown_overrides)}")
        for name, variables in hosts.items():
            per_node = {
                "k3s_flannel_iface": node_flannel.get(name) if name in node_flannel else prompt(
                    f"{name} Flannel interface override (blank to inherit)", str(variables.get("k3s_flannel_iface", ""))
                ),
                "netplan_dhcp_interface": node_dhcp_interfaces.get(name) if name in node_dhcp_interfaces else prompt(
                    f"{name} DHCP interface override (blank to inherit)", str(variables.get("netplan_dhcp_interface", ""))
                ),
                "netplan_dhcp_definition": node_dhcp_definitions.get(name) if name in node_dhcp_definitions else prompt(
                    f"{name} Netplan definition override (blank to inherit)", str(variables.get("netplan_dhcp_definition", ""))
                ),
            }
            for key, value in per_node.items():
                if value:
                    variables[key] = value
                else:
                    variables.pop(key, None)

        all_vars["ansible_user"] = ansible_user
        all_vars["k3s_version"] = k3s_version
        settings = {
            "k3s_lan_cidr": str(ipaddress.ip_network(lan, strict=False)),
            "k3s_cluster_cidr": str(ipaddress.ip_network(pods, strict=False)),
            "k3s_service_cidr": str(ipaddress.ip_network(services, strict=False)),
            "k3s_resolv_conf": resolv,
            "k3s_dns_servers": [str(ipaddress.ip_address(value)) for value in dns],
            "k3s_flannel_iface": flannel,
            "k3s_snapshotter": snapshotter,
            "netplan_dhcp_apply": bool(dhcp_apply),
            "netplan_dhcp_interface": dhcp_interface,
            "netplan_dhcp_definition": dhcp_definition,
            "default_gateway_lan_cidr": "{{ k3s_lan_cidr }}",
            "default_gateway_lan_interface": args.gateway_lan_interface if args.gateway_lan_interface is not None else prompt(
                "Gateway LAN interface (blank for automatic)", str(defaults["default_gateway_lan_interface"])
            ),
            "default_gateway_wan_interface": args.gateway_wan_interface if args.gateway_wan_interface is not None else prompt(
                "Gateway WAN interface (blank for automatic)", str(defaults["default_gateway_wan_interface"])
            ),
        }
        for key in settings:
            all_vars.pop(key, None)
        validate_networks(settings, hosts)
        print("Validating SSH, sudo, operating system, and service-node architecture...")
        for name, variables in hosts.items():
            preflight_host(
                str(variables["ansible_host"]),
                str(variables.get("ansible_user", ansible_user)),
                require_amd64=name in service_nodes,
            )
        inventory_backup = write_yaml(INVENTORY_PATH, inventory)
        settings_backup = write_yaml(GROUP_VARS_PATH, settings)
        print(f"Initialized {len(hosts)} node(s) in {INVENTORY_PATH}.")
        if inventory_backup:
            print(f"Previous inventory: {inventory_backup}")
        if settings_backup:
            print(f"Previous settings: {settings_backup}")
    except (JihwijaError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()

from __future__ import annotations

import ipaddress
from pathlib import Path

import yaml


TEST_ENV = Path(__file__).parent / "test-env"


def _load(name: str) -> dict:
    return yaml.safe_load((TEST_ENV / name).read_text())


def test_compose_addresses_match_ansible_inventory() -> None:
    compose = _load("docker-compose.yml")
    inventory = _load("inventory.yml")

    subnet = ipaddress.ip_network(
        compose["networks"]["cluster"]["ipam"]["config"][0]["subnet"]
    )
    inventory_hosts = {
        host: variables
        for group in inventory["all"]["children"].values()
        for host, variables in group["hosts"].items()
    }
    compose_hosts = {
        service["hostname"]: service["networks"]["cluster"]["ipv4_address"]
        for service in compose["services"].values()
        if "hostname" in service
    }

    assert set(compose_hosts) == set(inventory_hosts)
    assert inventory["all"]["vars"]["k3s_lan_cidr"] == str(subnet)
    for host, address in compose_hosts.items():
        assert inventory_hosts[host]["ansible_host"] == address
        assert ipaddress.ip_address(address) in subnet


def test_inventory_has_one_server_gateway_and_service_node() -> None:
    inventory = _load("inventory.yml")
    hosts = [
        variables
        for group in inventory["all"]["children"].values()
        for variables in group["hosts"].values()
    ]

    assert sum(host.get("k3s_host", False) for host in hosts) == 1
    assert sum(host.get("is_default_gateway", False) for host in hosts) == 1
    assert sum(host.get("is_jihwija_service_node", False) for host in hosts) >= 1
    assert inventory["all"]["vars"]["k3s_snapshotter"] == "native"

    networks = [
        ipaddress.ip_network(inventory["all"]["vars"][name])
        for name in ("k3s_lan_cidr", "k3s_cluster_cidr", "k3s_service_cidr")
    ]
    assert all(
        not left.overlaps(right)
        for index, left in enumerate(networks)
        for right in networks[index + 1 :]
    )

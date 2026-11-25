#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from lib.config_env import JIHWIJA_ENV, load_jihwija_env_or_exit

HOSTNAME_VARIABLES = ("RANCHER_HOSTNAME", "HARBOR_HOSTNAME", "PORTAINER_HOSTNAME", "ARGO_HOSTNAME")
CHART_NAMES = {
    "cert-manager": "cert-manager",
    "nvidia": "nvidia-device-plugin",
    "rancher": "rancher",
    "harbor": "harbor",
    "portainer": "portainer",
    "argo": "argo-workflows",
}
WORKLOAD_SELECTORS = {
    "cert-manager": ("cert-manager", "app.kubernetes.io/instance=cert-manager"),
    "nvidia": ("nvidia-device-plugin", "app.kubernetes.io/instance=nvidia-device-plugin"),
    "rancher": ("cattle-system", "app=rancher"),
    "harbor": ("jihwija-system", "app.kubernetes.io/instance=harbor"),
    "portainer": ("jihwija-system", "app.kubernetes.io/instance=portainer"),
    "argo": ("jihwija-system", "app.kubernetes.io/instance=argo-workflows"),
}
load_jihwija_env_or_exit()


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def kubectl_base() -> list[str]:
    if shutil.which("k3s"):
        return ["k3s", "kubectl"]
    if shutil.which("kubectl"):
        return ["kubectl"]
    die("Neither k3s nor kubectl was found in PATH.")


def command(args: list[str], **kwargs):
    return subprocess.run([*kubectl_base(), *args], **kwargs)


def validate_hostname(variable: str, value: str) -> None:
    label = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
    if len(value) > 253 or not value or any(not label.fullmatch(part) for part in value.split(".")):
        die(f"{variable} must be a valid DNS hostname without a scheme or path.")


def configured_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for variable in HOSTNAME_VARIABLES:
        value = os.environ.get(variable, "").strip()
        if not value:
            die(f"{variable} is not set in {JIHWIJA_ENV}.")
        validate_hostname(variable, value)
        values[variable] = value
    rancher = os.environ.get("RANCHER_BOOTSTRAP_PASSWORD", "")
    harbor = os.environ.get("HARBOR_ADMIN_PASSWORD", "")
    if not rancher or "\n" in rancher or "\r" in rancher:
        die("RANCHER_BOOTSTRAP_PASSWORD must be set and contain no newline.")
    if not harbor or "\n" in harbor or "\r" in harbor:
        die("HARBOR_ADMIN_PASSWORD must be set and contain no newline.")
    values["RANCHER_BOOTSTRAP_PASSWORD_JSON"] = json.dumps(rancher)
    values["HARBOR_ADMIN_PASSWORD_B64"] = base64.b64encode(harbor.encode()).decode()
    return values


def render(service: str | None) -> str:
    services = Path(__file__).resolve().parents[2] / "jihwija-services"
    if service == "nvidia":
        # GPU discovery is cluster infrastructure and has no dependency on
        # service hostnames or credentials, so K3s installation can bootstrap
        # it independently of the rest of the bundle.
        return (services / "nvidia-device-plugin.yaml").read_text()
    result = command(["kustomize", str(services)], check=True, capture_output=True, text=True)
    rendered = result.stdout
    for variable, value in configured_values().items():
        placeholder = "${" + variable + "}"
        if placeholder not in rendered:
            die(f"The rendered manifests do not contain {placeholder}.")
        rendered = rendered.replace(placeholder, value)
    if "${" in rendered:
        die("The rendered manifests contain an unresolved environment placeholder.")
    if not service:
        return rendered
    chart = CHART_NAMES[service]
    selected = []
    for document in yaml.safe_load_all(rendered):
        if not document:
            continue
        kind = document.get("kind")
        name = document.get("metadata", {}).get("name")
        if (kind == "Namespace" and name == "jihwija-system") or (
            kind == "HelmChart" and name == chart
        ) or (
            service == "harbor" and kind == "Secret" and name == "harbor-admin-password"
        ):
            selected.append(document)
    if not selected:
        die(f"No rendered resources were found for {service}.")
    return "---\n".join(yaml.safe_dump(item, sort_keys=False) for item in selected)


def parse_duration(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([smh]?)", value)
    if not match:
        raise argparse.ArgumentTypeError("timeout must look like 90s, 30m, or 1h")
    return int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[match.group(2)]


def wait_for_harbor_database_before_upgrade() -> None:
    database = "statefulset/harbor-database"
    existing = command(
        ["get", database, "-n", "jihwija-system", "--ignore-not-found", "-o", "name"],
        check=True, capture_output=True, text=True,
    )
    if existing.stdout.strip():
        print("Waiting for the Harbor database before applying its Helm upgrade...")
        command(["rollout", "status", database, "-n", "jihwija-system", "--timeout=30m"], check=True)


def selected_workloads(service: str | None) -> dict[str, tuple[str, str]]:
    return {service: WORKLOAD_SELECTORS[service]} if service else WORKLOAD_SELECTORS


def find_workloads(namespace: str, selector: str) -> list[str]:
    result = command(
        ["get", "deployments,statefulsets,daemonsets", "-n", namespace, "-l", selector, "-o", "name"],
        check=True, capture_output=True, text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def restart_workloads(service: str | None) -> None:
    for name, (namespace, selector) in selected_workloads(service).items():
        resources = find_workloads(namespace, selector)
        if not resources:
            die(f"Cannot redeploy {name}: no managed workloads were found.")
        for resource in resources:
            command(["rollout", "restart", resource, "-n", namespace], check=True)


def wait_for_workloads(service: str | None, timeout: str) -> None:
    deadline = time.monotonic() + parse_duration(timeout)
    for name, (namespace, selector) in selected_workloads(service).items():
        resources: list[str] = []
        while time.monotonic() < deadline:
            resources = find_workloads(namespace, selector)
            if resources:
                break
            time.sleep(5)
        if not resources:
            die(f"No {name} workloads appeared before timeout.")
        for resource in resources:
            command(["rollout", "status", resource, "-n", namespace, f"--timeout={timeout}"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Jihwija-managed cluster services.")
    parser.add_argument("--redeploy", action="store_true")
    parser.add_argument("--timeout", default="30m")
    parser.add_argument("--service", choices=sorted(CHART_NAMES), help=argparse.SUPPRESS)
    args = parser.parse_args()
    parse_duration(args.timeout)
    if args.service in (None, "harbor"):
        wait_for_harbor_database_before_upgrade()
    command(["apply", "-f", "-"], check=True, input=render(args.service), text=True)
    if args.redeploy:
        restart_workloads(args.service)
    wait_for_workloads(args.service, args.timeout)
    if args.service in (None, "nvidia"):
        subprocess.run(
            [
                str(Path(__file__).resolve().parent / "k3s-taint-gpu-nodes.py"),
                "--wait-timeout",
                "30",
            ],
            check=True,
        )
    if args.service is None:
        subprocess.run([str(Path(__file__).resolve().parent / "trust-k3s-certs.py")], check=True)
    if args.service == "nvidia":
        return
    values = configured_values()
    variables = {"rancher": "RANCHER_HOSTNAME", "harbor": "HARBOR_HOSTNAME", "portainer": "PORTAINER_HOSTNAME", "argo": "ARGO_HOSTNAME"}
    for service, variable in variables.items():
        if args.service in (None, service):
            print(f"{service.title()}: https://{values[variable]}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


GPU_RESOURCE = "nvidia.com/gpu"
GPU_TAINT_VALUE = "true"
GPU_TAINT_EFFECT = "NoSchedule"


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def kubectl(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if "KUBECONFIG" not in env and Path("/etc/rancher/k3s/k3s.yaml").exists():
        env["KUBECONFIG"] = "/etc/rancher/k3s/k3s.yaml"
    try:
        return subprocess.run(
            ["kubectl", *args],
            check=True,
            capture_output=capture,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        die("kubectl was not found in PATH.")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "kubectl failed").strip()
        die(detail)


def nodes() -> list[dict]:
    result = kubectl("get", "nodes", "-o", "json", capture=True)
    return json.loads(result.stdout).get("items", [])


def gpu_node_names() -> list[str]:
    names = []
    for node in nodes():
        allocatable = node.get("status", {}).get("allocatable", {})
        try:
            gpu_count = int(allocatable.get(GPU_RESOURCE, "0"))
        except (TypeError, ValueError):
            gpu_count = 0
        if gpu_count > 0:
            names.append(node["metadata"]["name"])
    return names


def tainted_node_names() -> list[str]:
    names = []
    for node in nodes():
        taints = node.get("spec", {}).get("taints", [])
        if any(
            taint.get("key") == GPU_RESOURCE
            and taint.get("effect") == GPU_TAINT_EFFECT
            for taint in taints
        ):
            names.append(node["metadata"]["name"])
    return names

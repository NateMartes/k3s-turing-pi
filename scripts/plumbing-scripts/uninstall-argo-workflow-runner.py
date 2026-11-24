#!/usr/bin/env python3
import argparse
import os
import re
from pathlib import Path

from lib.platform_common import determine_username, die, require_root, run
from lib.user_privileges import revoke_privilege


def validate_namespace(namespace: str) -> str:
    if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?", namespace):
        die(
            "Namespace must be a lowercase Kubernetes DNS label containing only "
            "letters, digits, and '-' (max 63 characters)."
        )
    return namespace


def kubectl(args):
    env = os.environ.copy()
    if "KUBECONFIG" not in env and Path("/etc/rancher/k3s/k3s.yaml").exists():
        env["KUBECONFIG"] = "/etc/rancher/k3s/k3s.yaml"
    return run(["kubectl", *args], check=False, env=env)


def main():
    parser = argparse.ArgumentParser(
        description="Remove a user's Argo workflow runner RBAC from a namespace."
    )
    parser.add_argument("-u", "--username", required=True)
    parser.add_argument("-n", "--namespace", required=True)
    args = parser.parse_args()

    require_root()
    username = determine_username(args.username)
    namespace = validate_namespace(args.namespace)
    runner = "argo-workflow-runner"

    revoke_privilege(username, "argo-template-admin")
    print("Removed the user's Argo template administrator binding, if present.")

    kubectl(
        [
            "delete",
            "clusterrolebinding",
            f"{username}-argo-workflow-template-reader",
            "--ignore-not-found=true",
        ]
    )

    kubectl(
        [
            "delete",
            f"rolebinding/{runner}",
            f"rolebinding/{runner}-namespace-admin",
            f"role/{runner}",
            f"serviceaccount/{runner}",
            "--namespace",
            namespace,
            "--ignore-not-found=true",
        ]
    )
    print(f"Removed Argo workflow runner resources from {namespace}: {runner}")
    print("Removed the user's ClusterWorkflowTemplate reader binding.")


if __name__ == "__main__":
    main()

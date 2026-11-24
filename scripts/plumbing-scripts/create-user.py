#!/usr/bin/env python3
import argparse
import base64
import json
import os
import pwd
from pathlib import Path

from lib.user_common import (
    DEFAULT_ARGO_HOST, DEFAULT_HARBOR_HOST, DEFAULT_PORTAINER_HOST,
    DEFAULT_RANCHER_HOST,
    SELECTABLE_SERVICES, SELECTABLE_SERVICE_DEPENDENCIES,
    agent_address, choose_agent_port,
    die, generate_password, print_resource_summary, require_root, run, run_plumbing,
    save_state, set_quota, state_path, user_exists, validate_username, require_hostname,
    parse_services,
    DEFAULT_HARBOR_ADMIN_PASSWORD, DEFAULT_PORTAINER_API_KEY,
    DEFAULT_RANCHER_API_KEY, print_unverified_https_notice,
)


def validate_services(
    parser: argparse.ArgumentParser,
    selected: frozenset[str],
) -> None:
    conflicts = [
        f"{dependent} requires {dependency}"
        for dependent, dependencies in SELECTABLE_SERVICE_DEPENDENCIES.items()
        for dependency in dependencies
        if dependent in selected and dependency not in selected
    ]
    if conflicts:
        parser.error(
            "incompatible --only value: "
            + "; ".join(conflicts)
            + ". Include each required dependency too."
        )


def read_k3s_token(namespace: str, service_account: str) -> str:
    kubectl_env = os.environ.copy()
    if not kubectl_env.get("KUBECONFIG"):
        kubectl_env["KUBECONFIG"] = "/etc/rancher/k3s/k3s.yaml"

    result = run(
        [
            "kubectl",
            "--namespace", namespace,
            "get", "secret", f"{service_account}-token",
            "--output", "json",
        ],
        capture=True,
        env=kubectl_env,
    )
    secret = json.loads(result.stdout)
    encoded_token = secret.get("data", {}).get("token")
    if not encoded_token:
        die(
            f"Kubernetes Secret {namespace}/{service_account}-token does not "
            "contain a token."
        )
    return base64.b64decode(encoded_token, validate=True).decode("utf-8")


def main():
    p = argparse.ArgumentParser(
        description=(
            "Create a Linux user and provision their "
            "Docker/K3s/Argo/Harbor/Rancher/Portainer resources."
        )
    )
    p.add_argument("username_arg", nargs="?", metavar="USERNAME")
    p.add_argument("-u", "--username")
    p.add_argument(
        "-o", "--only",
        type=parse_services,
        default=None,
        metavar="SERVICE,...",
        help=(
            "Create resources only for these comma-separated services/features. "
            "Available: "
            + ", ".join(SELECTABLE_SERVICES)
            + ". Omit this option to create all services. Selected services "
            "must include their dependencies."
        ),
    )
    quota_options = p.add_mutually_exclusive_group()
    quota_options.add_argument(
        "-q", "--quota", default=None,
        help="Filesystem quota, e.g. 5GB or 500MB.",
    )
    quota_options.add_argument(
        "--no-quota",
        action="store_true",
        help="Do not prompt for or configure filesystem, K3s, or Harbor quotas.",
    )
    p.add_argument("--k3s-cpu-quota", default=None,
                   help="K3s namespace CPU quota. Default: 2.")
    p.add_argument("--k3s-memory-quota", default=None,
                   help="K3s namespace memory quota. Default: 6Gi.")
    p.add_argument("--k3s-storage-quota", default=None,
                   help="K3s namespace persistent and ephemeral storage quota. Default: 10Gi.")
    p.add_argument("--k3s-gpu-quota", default=None,
                   help="K3s namespace NVIDIA GPU quota. Default: 1.")
    p.add_argument("--rancher-host", default=DEFAULT_RANCHER_HOST)
    p.add_argument("--harbor-host", default=DEFAULT_HARBOR_HOST)
    p.add_argument("--portainer-host", default=DEFAULT_PORTAINER_HOST)
    p.add_argument("--cluster-id", default="local")
    p.add_argument("--agent-port", type=int, default=None)
    p.add_argument("--agent-address", default=None,
                   help="Address Portainer can use to reach this user's agent; defaults to this host FQDN:port.")
    p.add_argument("--shell", default="/bin/bash")
    p.add_argument(
        "--raw-logs", action="store_true",
        help="Stream all plumbing command output instead of using compact status lines.",
    )
    args = p.parse_args()
    if args.username and args.username_arg and args.username != args.username_arg:
        p.error("USERNAME and --username disagree")
    args.username = args.username or args.username_arg or input("Username: ").strip()
    if not args.username:
        p.error("a username is required")
    if args.only is None:
        selected = input(
            "Components to create [all] (comma-separated): "
        ).strip()
        args.only = (
            frozenset(SELECTABLE_SERVICES)
            if not selected or selected.lower() == "all"
            else parse_services(selected)
        )
    selected_services = args.only
    validate_services(p, selected_services)
    if args.no_quota and any((
        args.k3s_cpu_quota,
        args.k3s_memory_quota,
        args.k3s_storage_quota,
        args.k3s_gpu_quota,
    )):
        p.error("--no-quota cannot be combined with K3s quota options")

    require_root()
    if "rancher" in selected_services:
        args.rancher_host = require_hostname(
            args.rancher_host, "RANCHER_HOSTNAME", "--rancher-host"
        )
    if "harbor" in selected_services:
        args.harbor_host = require_hostname(
            args.harbor_host, "HARBOR_HOSTNAME", "--harbor-host"
        )
    if "portainer" in selected_services or "portainer-agent" in selected_services:
        args.portainer_host = require_hostname(
            args.portainer_host, "PORTAINER_HOSTNAME", "--portainer-host"
        )
    https_services = []
    if "harbor" in selected_services:
        https_services.append(("Harbor", args.harbor_host))
    if "rancher" in selected_services:
        https_services.append(("Rancher", args.rancher_host))
    if "portainer" in selected_services or "portainer-agent" in selected_services:
        https_services.append(("Portainer", args.portainer_host))
    print_unverified_https_notice(https_services)
    username = validate_username(args.username)
    linux_user_preexists = user_exists(username)
    if state_path(username).exists():
        die(f"A state file already exists for {username}; remove/reconcile it first.")

    quota = None
    if not args.no_quota:
        quota = args.quota or input(
            "Filesystem quota for user (for example 5GB): "
        ).strip()
    if "k3s-namespace" in selected_services and not args.no_quota:
        k3s_cpu_quota = (
            args.k3s_cpu_quota or input("K3s CPU quota [2]: ").strip() or "2"
        )
        k3s_memory_quota = (
            args.k3s_memory_quota or input("K3s memory quota [6Gi]: ").strip() or "6Gi"
        )
        k3s_storage_quota = (
            args.k3s_storage_quota
            or input("K3s storage quota [10Gi]: ").strip()
            or "10Gi"
        )
        k3s_gpu_quota = (
            args.k3s_gpu_quota or input("K3s GPU quota [1]: ").strip() or "1"
        )
    else:
        k3s_cpu_quota = None
        k3s_memory_quota = None
        k3s_storage_quota = None
        k3s_gpu_quota = None
    password = generate_password()
    needs_agent_details = (
        "portainer-agent" in selected_services or "portainer" in selected_services
    )
    agent_port = None
    agent_addr = None
    if needs_agent_details:
        agent_port = args.agent_port or choose_agent_port()
        agent_addr = args.agent_address or agent_address(agent_port)

    state = {
        "username": username,
        "services": sorted(selected_services),
        "quota": quota,
        "filesystem_quota": not args.no_quota,
        "rancher_host": args.rancher_host,
        "harbor_host": args.harbor_host,
        "portainer_host": args.portainer_host,
        "argo_host": DEFAULT_ARGO_HOST,
        "cluster_id": args.cluster_id,
        "agent_port": agent_port,
        "agent_address": agent_addr,
        "namespace": f"{username}-namespace",
        "k3s_service_account": f"{username}-user",
        "k3s_cpu_quota": k3s_cpu_quota,
        "k3s_memory_quota": k3s_memory_quota,
        "k3s_storage_quota": k3s_storage_quota,
        "k3s_gpu_quota": k3s_gpu_quota,
        "k3s_quota": not args.no_quota,
        "rancher_user": username,
        "rancher_project": f"{username}-project",
        "harbor_user": username,
        "harbor_project": f"{username}-namespace",
        "harbor_storage_quota_bytes": (
            None if args.no_quota else 10 * 1024 * 1024 * 1024
        ),
        "harbor_quota": not args.no_quota,
        "portainer_user": username,
        "portainer_environment": f"{username}-docker",
        "docker_rootless": False,
        "portainer_agent": False,
        "k3s_namespace": False,
        "argo_workflow_runner": False,
        "harbor_account": False,
        "rancher_account": False,
        "portainer_account": False,
        "linux_user_created": not linux_user_preexists,
    }

    try:
        if linux_user_preexists:
            print(f"Using existing Linux user {username}...")
        else:
            print(f"Creating Linux user {username}...")
            run(["useradd", "--create-home", "--shell", args.shell, username])
            run(["chpasswd"], input_data=f"{username}:{password}\n")
        u = pwd.getpwnam(username)
        state["uid"] = u.pw_uid
        state["home"] = u.pw_dir
        state["linux_user"] = True

        if args.no_quota:
            print("Quota configuration disabled by --no-quota.")
        else:
            state.update(set_quota(username, quota))
        save_state(username, state)

        if "docker-rootless" in selected_services:
            print("\n[1/7] Installing rootless Docker")
            run_plumbing(
                "install-docker-rootless.py", ["-u", username],
                raw_logs=args.raw_logs, label="Installing rootless Docker",
            )
            state["docker_rootless"] = True
            save_state(username, state)
        else:
            print("\n[1/7] Skipping rootless Docker (not selected by --only)")

        if "portainer-agent" in selected_services:
            print("\n[2/7] Installing Portainer Agent")
            agent_args = [
                "-u", username,
                "-H", args.portainer_host,
                "--port", str(agent_port),
            ]
            run_plumbing(
                "install-portainer-agent.py", agent_args,
                raw_logs=args.raw_logs, label="Starting Portainer Agent",
            )
            state["portainer_agent"] = True
            save_state(username, state)
        else:
            print("\n[2/7] Skipping Portainer Agent (not selected by --only)")

        k3s_token = None
        if "k3s-namespace" in selected_services:
            print("\n[3/7] Creating K3s namespace")
            k3s_args = ["-u", username]
            if args.no_quota:
                k3s_args.append("--no-quota")
            else:
                k3s_args.extend([
                    "--cpu-quota", k3s_cpu_quota,
                    "--memory-quota", k3s_memory_quota,
                    "--storage-quota", k3s_storage_quota,
                    "--gpu-quota", k3s_gpu_quota,
                ])
            run_plumbing(
                "install-k3s-namespace.py",
                k3s_args,
                raw_logs=args.raw_logs,
                label="Creating K3s namespace",
            )
            state["k3s_namespace"] = True
            save_state(username, state)
            k3s_token = read_k3s_token(state["namespace"], f"{username}-user")
        else:
            print("\n[3/7] Skipping K3s namespace (not selected by --only)")

        if "argo-workflow-runner" in selected_services:
            print("\n[4/7] Installing Argo workflow runner")
            run_plumbing(
                "install-argo-workflow-runner.py",
                ["-u", username, "-n", state["namespace"]],
                raw_logs=args.raw_logs,
                label="Installing Argo workflow runner",
            )
            state["argo_workflow_runner"] = True
            save_state(username, state)
        else:
            print("\n[4/7] Skipping Argo workflow runner (not selected by --only)")

        if "harbor" in selected_services:
            print("\n[5/7] Creating Harbor account/project")
            harbor_args = ["-u", username, "-H", args.harbor_host]
            if args.no_quota:
                harbor_args.append("--no-quota")
            run_plumbing(
                "install-harbor-account.py",
                harbor_args,
                extra_env={
                    "USER_PASSWORD": password,
                    **(
                        {"HARBOR_ADMIN_PASSWORD": DEFAULT_HARBOR_ADMIN_PASSWORD}
                        if DEFAULT_HARBOR_ADMIN_PASSWORD
                        else {}
                    ),
                },
                raw_logs=args.raw_logs,
                label="Creating Harbor account and project",
            )
            state["harbor_account"] = True
            save_state(username, state)
        else:
            print("\n[5/7] Skipping Harbor account/project (not selected by --only)")

        if "rancher" in selected_services:
            print("\n[6/7] Creating Rancher account/project")
            rancher_args = ["-u", username, "-H", args.rancher_host]
            if args.cluster_id:
                rancher_args += ["--cluster-id", args.cluster_id]
            run_plumbing(
                "install-rancher-account.py",
                rancher_args,
                extra_env={
                    "USER_PASSWORD": password,
                    "RANCHER_TOKEN": DEFAULT_RANCHER_API_KEY
                },
                raw_logs=args.raw_logs,
                label="Creating Rancher account and project",
            )
            state["rancher_account"] = True
            save_state(username, state)
        else:
            print("\n[6/7] Skipping Rancher account/project (not selected by --only)")

        if "portainer" in selected_services:
            print("\n[7/7] Creating Portainer account/environment")
            portainer_args = [
                "-u", username,
                "-H", args.portainer_host,
                "--agent-address", agent_addr,
                "--agent-port", str(agent_port),
            ]
            run_plumbing(
                "install-portainer-account.py",
                portainer_args,
                extra_env={
                    "USER_PASSWORD": password,
                    "PORTAINER_API_KEY": DEFAULT_PORTAINER_API_KEY
                },
                raw_logs=args.raw_logs,
                label="Creating Portainer account and environment",
            )
            state["portainer_account"] = True
            save_state(username, state)
        else:
            print("\n[7/7] Skipping Portainer account/environment (not selected by --only)")

    except Exception:
        print("\nProvisioning stopped before completion.")
        print(f"Partial state has been saved to {state_path(username)}.")
        print("Run remove-user.py for this username to clean up the resources that were created.")
        raise

    print_resource_summary(
        state,
        include_password=password,
        include_k3s_token=k3s_token,
        include_linux_password=not linux_user_preexists,
    )

if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

from .platform_common import die, run


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PrivilegeDefinition:
    token: str
    description: str
    manifest_template: Path
    binding_name_template: str

    def binding_name(self, username: str) -> str:
        return self.binding_name_template.format(username=username)


PRIVILEGES = {
    "argo-template-admin": PrivilegeDefinition(
        token="argo-template-admin",
        description=(
            "create, update, and delete shared Argo ClusterWorkflowTemplate resources"
        ),
        manifest_template=(
            PROJECT_ROOT
            / "argo"
            / "argo-template-admin.yml"
        ),
        binding_name_template="{username}-argo-cluster-workflow-template-admin",
    ),
}


def validate_username(username: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        die(
            "Username must start with a lowercase letter or underscore and contain "
            "only lowercase letters, digits, '_' or '-' (max 32 characters)."
        )
    return username


def managed_identity(username: str) -> tuple[str, str]:
    username = validate_username(username)
    return f"{username}-namespace", f"{username}-user"


def kubectl(args, *, check=True, capture=False, input_data=None):
    env = os.environ.copy()
    admin_config = Path("/etc/rancher/k3s/k3s.yaml")
    if "KUBECONFIG" not in env and admin_config.exists():
        env["KUBECONFIG"] = str(admin_config)
    return run(
        ["kubectl", *args],
        check=check,
        capture=capture,
        env=env,
        input_data=input_data,
    )


def render_privilege_manifest(
    definition: PrivilegeDefinition,
    username: str,
) -> str:
    namespace, service_account = managed_identity(username)
    try:
        source = definition.manifest_template.read_text()
    except OSError as exc:
        die(f"Could not read privilege manifest {definition.manifest_template}: {exc}")
    return Template(source).substitute(
        USERNAME=username,
        NAMESPACE=namespace,
        SERVICE_ACCOUNT=service_account,
    )


def grant_privilege(username: str, privilege: str) -> PrivilegeDefinition:
    definition = PRIVILEGES[privilege]
    namespace, service_account = managed_identity(username)

    namespace_result = kubectl(
        ["get", "namespace", namespace], check=False, capture=True
    )
    if namespace_result.returncode != 0:
        die(
            f"Managed namespace '{namespace}' does not exist. Create the user's "
            "K3s namespace before granting this privilege."
        )

    service_account_result = kubectl(
        [
            "get",
            "serviceaccount",
            service_account,
            "--namespace",
            namespace,
        ],
        check=False,
        capture=True,
    )
    if service_account_result.returncode != 0:
        die(
            f"Managed service account '{namespace}/{service_account}' does not "
            "exist. Reconcile the user's K3s namespace before granting this privilege."
        )

    manifest = render_privilege_manifest(definition, username)
    kubectl(["apply", "-f", "-"], input_data=manifest)
    return definition


def revoke_privilege(username: str, privilege: str) -> PrivilegeDefinition:
    definition = PRIVILEGES[privilege]
    username = validate_username(username)
    kubectl(
        [
            "delete",
            "clusterrolebinding",
            definition.binding_name(username),
            "--ignore-not-found=true",
        ]
    )
    return definition

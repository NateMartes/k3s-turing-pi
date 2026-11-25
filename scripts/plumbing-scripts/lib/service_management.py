from __future__ import annotations

from pathlib import Path

import yaml

from .jihwija_common import JihwijaError, SERVICES_DIR, atomic_write


SERVICE_MANIFESTS = {
    "cert-manager": "cert-manager.yaml",
    "argo": "argo-workflows.yaml",
    "nvidia": "nvidia-device-plugin.yaml",
    "rancher": "rancher.yaml",
    "harbor": "harbor.yaml",
    "portainer": "portainer.yaml",
}

CHART_NAMES = {
    "cert-manager": "cert-manager",
    "argo": "argo-workflows",
    "nvidia": "nvidia-device-plugin",
    "rancher": "rancher",
    "harbor": "harbor",
    "portainer": "portainer",
}

KUSTOMIZATION_PATH = SERVICES_DIR / "kustomization.yaml"


def load_kustomization(path: Path = KUSTOMIZATION_PATH) -> dict:
    try:
        document = yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:
        raise JihwijaError(f"Service Kustomization was not found: {path}") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise JihwijaError(f"Could not read service Kustomization {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("resources"), list):
        raise JihwijaError(f"Expected {path} to contain a resources list.")
    if not all(isinstance(resource, str) for resource in document["resources"]):
        raise JihwijaError(f"Expected every resource in {path} to be a string.")
    return document


def enabled_services(path: Path = KUSTOMIZATION_PATH) -> list[str]:
    resources = set(load_kustomization(path)["resources"])
    return [
        service
        for service, manifest in SERVICE_MANIFESTS.items()
        if manifest in resources
    ]


def set_service_enabled(
    service: str,
    enabled: bool,
    path: Path = KUSTOMIZATION_PATH,
) -> bool:
    if service not in SERVICE_MANIFESTS:
        raise JihwijaError(f"Unknown Jihwija service: {service}")

    document = load_kustomization(path)
    resources = document["resources"]
    manifest = SERVICE_MANIFESTS[service]
    currently_enabled = manifest in resources
    if currently_enabled == enabled:
        return False

    known_manifests = set(SERVICE_MANIFESTS.values())
    selected = {
        resource
        for resource in resources
        if resource in known_manifests
    }
    if enabled:
        selected.add(manifest)
    else:
        selected.discard(manifest)

    # Keep non-service resources and extensions in their existing order, then
    # restore service manifests in their canonical dependency-friendly order.
    remaining = [resource for resource in resources if resource not in known_manifests]
    document["resources"] = [
        *remaining,
        *(
            candidate
            for candidate in SERVICE_MANIFESTS.values()
            if candidate in selected
        ),
    ]
    atomic_write(path, yaml.safe_dump(document, sort_keys=False), 0o644)
    return True

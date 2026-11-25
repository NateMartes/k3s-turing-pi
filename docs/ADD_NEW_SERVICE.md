---
title: JIHWIJA-ADD-SERVICE
section: 7
header: Jihwija Manual
footer: Jihwija
man-name: jihwija-add-service
description: add a Helm-managed service to the Jihwija service bundle
---

# Adding a New Service to Jihwija

Jihwija deploys cluster services through K3s's Helm Controller. Each managed
service normally has a `HelmChart` manifest in `jihwija-services/`, an entry in
the service registry, and a workload selector that Jihwija uses to wait for the
installation to become ready.

After a service is registered, operators can manage it with the standard CLI:

```bash
sudo jihwija enable service <name>
sudo jihwija disable service <name>
```

Enabling a service adds its manifest to the Kustomize resources and deploys
that service. Disabling it removes the manifest from Kustomize, deletes its
`HelmChart`, and reconciles the services that remain enabled.

## Files involved

| File | Purpose |
| :--- | :--- |
| `jihwija-services/<name>.yaml` | Defines the K3s `HelmChart` and any supporting resources. |
| `jihwija-services/kustomization.yaml` | Selects services that are enabled by default. |
| `scripts/plumbing-scripts/lib/service_management.py` | Maps the CLI service name to its manifest and HelmChart name. |
| `scripts/plumbing-scripts/deploy-services.py` | Renders configuration and waits for the service's workloads. |
| `scripts/plumbing-scripts/set-hostname.py` | Registers a hostname if the service exposes an ingress. |
| `scripts/plumbing-scripts/set-secret.py` | Allowlists secrets that operators may store with the CLI. |
| `etc/jihwija.env.example` | Documents configuration required by the service. |

The hostname, secret, and environment-example changes are optional when the
service does not need them.

## 1. Choose stable names

Choose three names before adding code:

- **CLI name:** the value accepted by `jihwija enable service`, such as
  `metrics-server`.
- **Manifest filename:** normally `<cli-name>.yaml`.
- **HelmChart name:** the value in `metadata.name`. It may differ from the CLI
  name when the upstream chart has an established release name.

Keep the CLI name and its manifest mapping stable. The manifest filename is
stored in the persisted enabled-service configuration in
`jihwija-services/kustomization.yaml`.

## 2. Add the HelmChart manifest

Create `jihwija-services/<name>.yaml`. A minimal service looks like this:

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: metrics-server
  namespace: kube-system
  labels:
    app.kubernetes.io/part-of: jihwija
spec:
  chart: metrics-server
  repo: https://kubernetes-sigs.github.io/metrics-server/
  version: 3.13.0
  targetNamespace: kube-system
  createNamespace: true
  timeout: 10m
  backOffLimit: 20
  valuesContent: |-
    # Pin the values required by this cluster here.
```

Follow these conventions:

- Put the `HelmChart` object in `kube-system`; that is where the K3s Helm
  Controller watches Jihwija's chart definitions.
- Pin the chart version and any image versions that must not drift.
- Set `targetNamespace` to the namespace where the chart's workloads should
  run.
- Add `app.kubernetes.io/part-of: jihwija` to the HelmChart metadata.
- Use `jihwija-services=true` node selection when the service must run on the
  designated AMD64 service node.
- Prefer chart values over separate supporting objects when possible. The
  generic disable operation removes the HelmChart, while deliberately leaving
  independent Secrets and persistent data intact.

If the manifest contains a Secret, do not commit a plaintext credential. Use
an environment placeholder and add the corresponding protected rendering
logic described below.

## 3. Register the service

Add the service to both mappings in
`scripts/plumbing-scripts/lib/service_management.py`:

```python
SERVICE_MANIFESTS = {
    # Existing services...
    "metrics-server": "metrics-server.yaml",
}

CHART_NAMES = {
    # Existing services...
    "metrics-server": "metrics-server",
}
```

`SERVICE_MANIFESTS` controls the CLI choices and the manifest added or removed
by the enable and disable commands. `CHART_NAMES` identifies the HelmChart to
render or delete.

The order of `SERVICE_MANIFESTS` is also the canonical Kustomize order. Place a
service after anything it depends on. For example, an ingress that requires
cert-manager should come after `cert-manager`. This keeps rendered output
predictable, but it does not sequence Helm Controller reconciliation; configure
the chart to tolerate a prerequisite that is still becoming ready.

## 4. Add the readiness selector

Add an entry to `WORKLOAD_SELECTORS` in
`scripts/plumbing-scripts/deploy-services.py`:

```python
WORKLOAD_SELECTORS = {
    # Existing services...
    "metrics-server": (
        "kube-system",
        "app.kubernetes.io/instance=metrics-server",
    ),
}
```

The tuple contains the workload namespace and a Kubernetes label selector.
Jihwija searches Deployments, StatefulSets, and DaemonSets with that selector,
then waits for every match to complete its rollout.

Render the chart or inspect an existing installation to verify the label:

```bash
sudo k3s kubectl get deployments,statefulsets,daemonsets \
  --namespace kube-system \
  --selector app.kubernetes.io/instance=metrics-server \
  --output name
```

The selector must be specific enough not to match unrelated workloads, and at
least one matching workload must appear after installation. If a chart does
not put one stable label on all workloads, select its primary workload or add
a stable common label through chart values.

## 5. Choose whether it is enabled by default

To enable the new service in fresh installations, add its manifest to
`jihwija-services/kustomization.yaml` in the same dependency order used by
`SERVICE_MANIFESTS`:

```yaml
resources:
  # Existing resources...
  - metrics-server.yaml
```

Leave it out when the service should be opt-in. Because it is registered in
`SERVICE_MANIFESTS`, an operator can still add it later with:

```bash
sudo jihwija enable service metrics-server
```

The installer preserves the deployed copy of `kustomization.yaml` during an
upgrade, so an operator's enabled-service selection is not reset by a new
Jihwija release.

## 6. Add hostnames and protected configuration when needed

### Hostnames

If the service exposes an ingress, add a variable such as
`METRICS_SERVER_HOSTNAME` to:

1. `VARIABLES` in `scripts/plumbing-scripts/set-hostname.py`.
2. `HOSTNAME_VARIABLES` in `scripts/plumbing-scripts/deploy-services.py`.
3. The service-to-variable mapping printed at the end of
   `deploy-services.py`.
4. `etc/jihwija.env.example` and the test environment when applicable.

Use the variable in the manifest as an exact placeholder:

```yaml
valuesContent: |-
  ingress:
    enabled: true
    hosts:
      - ${METRICS_SERVER_HOSTNAME}
```

Operators can then configure it with:

```bash
sudo jihwija set hostname metrics-server metrics.example.com
```

Jihwija's certificate-trust operation discovers TLS ingresses from the
cluster, so a normal ingress does not need a second hostname registry.

### Secrets

To accept a new protected value through `jihwija set secret`, add its variable
name to the allowlist in `scripts/plumbing-scripts/set-secret.py` and document
it in `etc/jihwija.env.example`.

Then extend `configured_values()` in `deploy-services.py` to validate and
transform it. The renderer only replaces variables it explicitly recognizes.
Use JSON encoding for a value embedded as YAML text or base64 encoding for a
Kubernetes Secret field, following the existing Rancher and Harbor patterns.

Never place the raw secret in a command line, committed manifest, generated
documentation, or test fixture intended for production.

## 7. Include supporting resources in single-service deployment

A full `jihwija deploy` renders every resource listed by Kustomize. In
contrast, `jihwija enable service <name>` asks `render()` in
`deploy-services.py` for only that service. The generic selection includes:

- The shared `jihwija-system` Namespace.
- The service's HelmChart.
- Harbor's password Secret as an existing special case.

If the new manifest contains a required Secret, ConfigMap, RBAC object, or
other supporting resource outside the chart, extend the selection in
`render()` so enabling that service applies those objects too. Give each
supporting resource an unambiguous name or label and test that it is not
selected for another service.

The generic disable path deletes only the service's HelmChart. This lets Helm
uninstall chart-managed resources while retaining independent credentials and
persistent data for a later re-enable. If a supporting object must also be
deleted, add narrowly scoped cleanup to `disable-service.py`; do not delete a
namespace shared with other services.

If the service needs a pre-deployment wait or a post-deployment action, add it
to `main()` in `deploy-services.py`. Guard the action with both the selected
service and `active_services`, following the Harbor database wait and NVIDIA
GPU-taint examples. A normal full deployment must not run the hook for a
disabled service.

## 8. Add user lifecycle integration only when required

Some services have per-user accounts or projects. If the new service does,
decide how it participates in:

- `create-user.py` and `remove-user.py`.
- `change-user-password.py`.
- Service-specific install, uninstall, password, or quota plumbing scripts.
- The `--only` service choices used by user-management commands.

Keep cluster-service deployment separate from user provisioning. A service can
be correctly installed without automatically creating external accounts for
every Linux user.

## 9. Update documentation and tests

At minimum:

1. Add the service to `jihwija-services/README.md`, including prerequisites,
   configuration, and verification commands.
2. Add any public CLI or environment configuration to the relevant setup and
   reference documentation.
3. Add focused tests for new rendering, cleanup, or validation logic.
4. Add new executable plumbing commands to `SCRIPT_NAMES` in
   `tests/plumbing_harness.py`.

The repository test suite already checks that all YAML manifests parse, all
public routes point to executable plumbing, and every executable plumbing
script follows the command contract.

Run:

```bash
pytest
make -C docs check
```

## 10. Verify the service on a cluster

First render the complete Kustomize bundle and inspect the new HelmChart:

```bash
sudo k3s kubectl kustomize jihwija-services \
  | less
```

Do not apply that output directly when it contains `${...}` placeholders.
Deploy through Jihwija so configuration is validated and substituted:

```bash
sudo jihwija deploy
```

Verify the HelmChart, Helm Controller job, and workloads:

```bash
sudo k3s kubectl get helmchart metrics-server --namespace kube-system
sudo k3s kubectl get helmchartconfig --namespace kube-system
sudo k3s kubectl get jobs --namespace kube-system
sudo k3s kubectl get pods --all-namespaces \
  --selector app.kubernetes.io/instance=metrics-server
```

Finally, test both lifecycle commands:

```bash
sudo jihwija disable service metrics-server
sudo k3s kubectl get helmchart metrics-server \
  --namespace kube-system \
  --ignore-not-found

sudo jihwija enable service metrics-server
sudo k3s kubectl get helmchart metrics-server --namespace kube-system
```

Confirm that disabling the service does not disturb other services and that
enabling it waits successfully for the workload selector added earlier.

## Review checklist

- [ ] The HelmChart and image versions are pinned.
- [ ] The target namespace and node architecture are correct.
- [ ] The service is present in `SERVICE_MANIFESTS` and `CHART_NAMES`.
- [ ] `WORKLOAD_SELECTORS` matches at least one stable workload.
- [ ] Default-enabled status is represented in `kustomization.yaml`.
- [ ] Hostnames and secrets are validated and rendered without plaintext.
- [ ] Supporting resources work with single-service enable and disable.
- [ ] User lifecycle integration is added only if the service needs it.
- [ ] Documentation, unit tests, man pages, and cluster verification pass.

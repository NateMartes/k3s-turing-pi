# Jihwija Services

This Kustomize bundle deploys Rancher, Harbor, Portainer, Argo Workflows,
cert-manager, the NVIDIA device plugin, Loki, Grafana, Mimir, and Alloy to the
K3s cluster. Run the commands below from the repository root.

## Getting Started

### 1. Check the prerequisites

Before deploying, ensure that:

- K3s is running and `kubectl` can reach the cluster.
- NVIDIA GPU nodes have `nvidia-container-runtime` installed and detected by
  K3s as the `nvidia` RuntimeClass.
- Every service hostname resolves to an address served by the cluster's
  Traefik ingress.
- An AMD64 K3s node is marked `is_jihwija_service_node: true` in
  `ansible/inventory.yml`. The K3s setup playbook gives it the
  `jihwija-services=true` label used by Harbor, Portainer, and Argo.

The pinned stable Harbor release is scheduled to AMD64 because its complete
set of component images is not multi-architecture. The registry can still
store images for ARM64, AMD64, and other platforms.

### 2. Configure hostnames and initial credentials

Use Jihwija to store hostnames and initial credentials in the protected
`/opt/jihwija/etc/jihwija.env` file:

```bash
sudo jihwija set hostname rancher rancher.10.42.0.31.sslip.io
sudo jihwija set hostname harbor harbor.10.42.0.31.sslip.io
sudo jihwija set hostname portainer portainer.10.42.0.31.sslip.io
sudo jihwija set hostname argo argo.10.42.0.31.sslip.io
sudo jihwija set hostname grafana grafana.10.42.0.31.sslip.io
sudo jihwija set secret RANCHER_BOOTSTRAP_PASSWORD
sudo jihwija set secret HARBOR_ADMIN_PASSWORD
sudo jihwija set secret GRAFANA_ADMIN_PASSWORD
```

`HARBOR_ADMIN_PASSWORD` is the initial password for Harbor's built-in `admin`
account. `RANCHER_BOOTSTRAP_PASSWORD` is Rancher's first-login password. Change
both passwords in their respective interfaces after initial setup; changing
these environment variables later does not reset an existing installation.

Portainer prompts for its initial administrator account when first opened.
Afterward, create a Portainer API key and store it with
`sudo jihwija set secret PORTAINER_API_KEY`.

`ARGO_HOSTNAME` is the TLS hostname for the Argo Server API and UI. The Argo
CLI uses this endpoint to submit workflows while Argo Server enforces the
caller's Kubernetes RBAC permissions.

The managed Argo CLI profile sets `ARGO_INSECURE_SKIP_VERIFY=true` for this
HTTPS endpoint. The workflow controller and Argo Server use their Kubernetes
service accounts and the standard in-cluster API configuration. Do not set
`ARGO_INSECURE_SKIP_TLS_VERIFY` on those Pods: it selects Argo's explicit
Kubernetes-client configuration without supplying an API server address.

### 3. Remove a previous standalone Argo installation

If Argo was previously installed into an `argo` namespace with the upstream
release manifest, remove every namespaced component before deploying it as a
Jihwija service:

```bash
sudo k3s kubectl delete namespace argo --ignore-not-found
```

This command removes everything that lives in the old `argo` namespace. It
does not remove cluster-scoped resources. If the old installation came from
Argo's official `install.yaml`, remove its now-unused cluster RBAC and priority
class too:

```bash
sudo k3s kubectl delete clusterrolebinding \
  argo-binding argo-server-binding \
  --ignore-not-found
sudo k3s kubectl delete clusterrole \
  argo-aggregate-to-admin \
  argo-aggregate-to-edit \
  argo-aggregate-to-view \
  argo-cluster-role \
  argo-server-cluster-role \
  --ignore-not-found
sudo k3s kubectl delete priorityclass workflow-controller \
  --ignore-not-found
```

Do not delete the Argo CRDs or existing `ClusterWorkflowTemplate` objects. The
new Helm release adopts and updates the CRDs, and the shared templates remain
available to users. The cleanup above also leaves the repository's per-user
runner RBAC intact.

### 4. Deploy the services

Deploy through the CLI after configuration:

```bash
sudo jihwija deploy
```

Individual services can be removed from or restored to the managed bundle.
The supported names are `alloy`, `argo`, `cert-manager`, `grafana`, `harbor`,
`loki`, `mimir`, `nvidia`, `portainer`, and `rancher`:

```bash
sudo jihwija disable service harbor
sudo jihwija enable service harbor
```

The four observability services are deliberately independent. Alloy continues
retrying both destinations when Loki or Mimir is disabled, and Grafana keeps
both provisioned datasources. Mimir uses the pinned upstream
`mimir-distributed` chart with one replica of each component; every component
is selected onto the same `jihwija-services=true` node. See
[Observability Stack](../docs/OBSERVABILITY.md).

Disabling a service removes its manifest from `kustomization.yaml`, deletes its
K3s HelmChart, and reconciles the remaining enabled services. Enabling it adds
the manifest back and deploys that service. The selected service set is kept
across Jihwija upgrades.

The plumbing scripts read `/opt/jihwija/etc/jihwija.env` automatically.
Hostname changes offer to redeploy the affected service immediately.

Use this script instead of `kubectl apply -k`. Kubernetes does not expand the
environment-variable placeholders in the committed manifests, so the script
validates, renders, and replaces them in memory before applying the resources.
For an existing Harbor installation, the script also waits up to 30 minutes
for PostgreSQL to become ready before updating the Helm chart. This keeps the
pre-upgrade database migration job from starting while PostgreSQL is still
recovering. The script streams the database Pod logs during this wait.
It also prints the StatefulSet's ready-replica count every 10 seconds so the
gap between PostgreSQL startup messages and Kubernetes readiness is visible.

### 5. Check the deployment

Inspect the Helm installations and Pods:

```bash
sudo k3s kubectl get helmcharts -n kube-system
sudo k3s kubectl get pods -n jihwija-system
sudo k3s kubectl get pods -n cattle-system
sudo k3s kubectl get pods -n cert-manager
sudo k3s kubectl get pods -n nvidia-device-plugin
```

Confirm that Argo's cluster-scoped controller and client-authenticated server
are ready in `jihwija-system`:

```bash
sudo k3s kubectl rollout status \
  deployment/argo-workflows-workflow-controller \
  --namespace jihwija-system
sudo k3s kubectl rollout status deployment/argo-workflows-server \
  --namespace jihwija-system
sudo k3s kubectl logs deployment/argo-workflows-server \
  --namespace jihwija-system \
  --tail 100 | grep 'authModes="\[client\]"'
```

Harbor consists of several Pods and can take longer than Portainer to become
ready. If a Harbor Pod remains pending, verify that the selected Jihwija node
has both the `jihwija-services=true` and `kubernetes.io/arch=amd64` labels.
The NVIDIA chart installs Node Feature Discovery to locate compatible ARM64
GPU nodes automatically. On Jetson, NFD derives `nvidia.com/gpu.present=true`
from the loaded or built-in `nvidia` kernel module, or from the `-tegra` kernel
suffix used by the repository's Jetson build. These fallbacks are needed because
the integrated Tegra GPU does not provide the NVIDIA PCI label used by discrete
GPUs and its driver may not appear as a standalone `nvidia` entry in
`/proc/modules`. This bootstrap label schedules the device-plugin Pod; the Pod
then publishes the allocatable `nvidia.com/gpu` resource. The ARM64 constraint
keeps the plugin off AMD64 nodes that do not have the NVIDIA runtime configured.
The device plugin passes allocated GPUs by index so the Tegra GPU is presented
to the Jetson CSV runtime as device `0`; its default UUID-style identifier is
the literal value `tegra`, which the runtime cannot inject.

Check both discovery and the published GPU resource:

```bash
sudo k3s kubectl get nodes -L nvidia.com/gpu.present
sudo k3s kubectl get pods -n nvidia-device-plugin -o wide
sudo k3s kubectl get nodes \
  -o custom-columns='NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

`jihwija install k3s` installs this discovery support and automatically applies
the GPU taint. It is reconciled again when a node is added or the service bundle
is deployed. Maintainers can also run the same plumbing operation directly:

```bash
sudo ./scripts/plumbing-scripts/k3s-taint-gpu-nodes.py
```

This applies `nvidia.com/gpu=true:NoSchedule` to every node discovered by NFD
or advertising an allocatable GPU. GPU workloads must request
`nvidia.com/gpu: 1` and include the matching toleration. To allow ordinary
workloads on those nodes again:

```bash
sudo ./scripts/plumbing-scripts/k3s-untaint-gpu-nodes.py
```

### 6. Trust and distribute the private ingress certificates

After all four ingresses are available, discover their private certificate
authorities, configure containerd trust for every Jihwija-service hostname,
and distribute the resulting files to every Ready K3s node:

```bash
sudo ./scripts/plumbing-scripts/trust-k3s-certs.py
```

Harbor's official chart generates its ingress certificate automatically. The
trust script discovers that certificate and every hostname exposed by an
Ingress in `jihwija-system`; no duplicate hostname configuration is required.
It builds a bundle containing all discovered Jihwija-service CAs, merges a
`tls.ca_file` entry for every discovered Jihwija-service hostname into
`/etc/rancher/k3s/registries.yaml`, then uses SSH/SCP to install the
certificates and registry configuration on every node whose Kubernetes `Ready`
condition is `True`. Finally, it restarts K3s on each updated node so
containerd reloads the configuration. Entries for services that are not image
registries are harmless; containerd only uses an entry when an image reference
names that host as its registry.

The SSH user defaults to the account that invoked `sudo`. It must have
key-based access and passwordless `sudo` on every K3s node. Specify a different
remote account with `--ssh-user USER` when necessary.

Every node must be able to resolve `HARBOR_HOSTNAME` to the cluster's Traefik
ingress before it can pull images from the registry.

Kubernetes ConfigMaps, including the automatically mounted `kube-root-ca.crt`,
do not configure image-pull trust. The node's containerd process pulls images
before a Pod or Argo workflow container starts. If Harbor's private CA is only
installed in browsers, the control machine, or a Pod ConfigMap, workflows can
fail with `ErrImagePull` or `ImagePullBackOff` and an `x509: certificate signed
by unknown authority` event. The registry configuration and CA bundle must be
present on every schedulable K3s server and agent, followed by a K3s restart.

The script recursively merges the managed Jihwija-service TLS entries with
the local `registries.yaml`, preserving other registry mirrors, authentication,
and TLS settings, and creates a timestamped backup before changing it. That
merged file becomes the cluster source of truth and replaces each Ready node's
registry configuration; GNU `install` creates a numbered backup of an existing
remote file.

### 7. Open the services

- Harbor: `https://<HARBOR_HOSTNAME>`
- Portainer: `https://<PORTAINER_HOSTNAME>`
- Rancher: `https://<RANCHER_HOSTNAME>`
- Argo Workflows: `https://<ARGO_HOSTNAME>`
- Grafana: `https://<GRAFANA_HOSTNAME>`

If your computer cannot reach the cluster network directly, follow the
[SSH tunneling guide](../docs/TUNNELING.md).

For Harbor's initial setup, log in as `admin` with
`HARBOR_ADMIN_PASSWORD`. For Rancher, log in as `admin` with
`RANCHER_BOOTSTRAP_PASSWORD`. Portainer guides you through creation of its
initial administrator account. For Grafana, log in as `admin` with
`GRAFANA_ADMIN_PASSWORD`.

### 8. Log a container client into Harbor

After installing the private CA, authenticate a Docker-compatible client with:

```bash
printf '%s' "${HARBOR_ADMIN_PASSWORD}" | docker login "${HARBOR_HOSTNAME}" \
  --username admin \
  --password-stdin
```

Create a Harbor project before pushing images. Kubernetes workloads should use
a namespace-scoped `imagePullSecret` instead of embedding administrator
credentials in Pod specifications.

## Known Issues

### Harbor database startup on Linux 7.0.0-42

Ubuntu 26.04's `7.0.0-42-generic` kernel has an observed AppArmor regression
that can prevent Harbor's PostgreSQL container from starting. The problem
occurs when `kernel.apparmor_restrict_unprivileged_unconfined=1` causes the
containerd AppArmor profile to be stacked with `unconfined`. Signal delivery
inside the container can then fail with `EPERM`, disrupting PostgreSQL startup
or an on-disk database upgrade. Core and jobservice consequently fail to start
or remain unready because the database Pod never becomes ready.

Confirm the affected kernel and setting on the node that hosts Harbor:

```bash
uname -r
sysctl kernel.apparmor_restrict_unprivileged_unconfined
sudo journalctl -k --grep='apparmor.*DENIED'
```

The preferred workaround is to boot the node with the previous working kernel,
such as `7.0.0-38-generic`, until the regression is fixed. This preserves the
Ubuntu AppArmor hardening setting.

If booting an earlier kernel is not immediately possible, temporarily disable
only the affected restriction on every node that can run Harbor:

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0
echo 'kernel.apparmor_restrict_unprivileged_unconfined = 0' \
  | sudo tee /etc/sysctl.d/90-k3s-container-apparmor.conf
sudo sysctl --system
```

AppArmor labels are assigned when a container is created, so recreate the
database Pod after changing the setting:

```bash
sudo k3s kubectl delete pod harbor-database-0 -n jihwija-system
sudo k3s kubectl get pods -n jihwija-system --watch
```

Setting `kernel.apparmor_restrict_unprivileged_unconfined=0` relaxes one Ubuntu
AppArmor hardening control; it does not disable AppArmor entirely. Remove the
override and restore the value to `1` after installing a fixed kernel, then
recreate affected Pods. A detailed reproduction and explanation of the same
container signal-denial behavior is available in this
[AppArmor regression investigation](https://homelab2.e-whisper.com/how-to-guides/troubleshooting/apparmor-signal-denied/).

## Deployment Reference

### Namespace layout

- Harbor: `jihwija-system`
- Portainer: `jihwija-system`
- Argo Workflows controller and server: `jihwija-system`
- Rancher: `cattle-system`
- cert-manager: `cert-manager`
- NVIDIA device plugin and Node Feature Discovery: `nvidia-device-plugin`

Argo uses a cluster-scoped controller even though its control-plane Pods live
in `jihwija-system`; user Workflows and their Pods remain in their respective
user namespaces. Rancher remains in `cattle-system` because some Rancher
components assume that namespace. cert-manager remains in its conventional
`cert-manager` namespace because it is a singleton cluster dependency with
CRDs, webhooks, and cluster-scoped RBAC. The NVIDIA device plugin remains in
its own namespace because it is a cluster-level hardware discovery service.

All six `HelmChart` resources use this label so they remain logically grouped:

```yaml
app.kubernetes.io/part-of: jihwija
```

### Pinned versions

- Harbor: 2.15.4 (chart 1.19.4)
- Portainer CE: 2.45.2 (chart 245.2.0)
- Rancher: 2.15.0 (chart 2.15.1)
- Argo Workflows: v4.1.6 (chart 2.0.16)
- cert-manager: v1.21.2
- NVIDIA device plugin: 0.19.3

Harbor and Portainer use persistent `local-path` volumes. Their data remains on
the selected Jihwija-service node, so back up the corresponding PVC data
before replacing or reprovisioning that node.

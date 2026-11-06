# Sysadmin Services

This Kustomize bundle deploys Rancher, Harbor, Portainer, cert-manager, and the
NVIDIA device plugin to the K3s cluster. Run the commands below from the
repository root.

## Getting Started

### 1. Check the prerequisites

Before deploying, ensure that:

- K3s is running and `kubectl` can reach the cluster.
- NVIDIA GPU nodes have `nvidia-container-runtime` installed and detected by
  K3s as the `nvidia` RuntimeClass.
- Every service hostname resolves to an address served by the cluster's
  Traefik ingress.
- An AMD64 K3s node is marked `is_sysadmin_service_node: true` in
  `ansible/inventory.yml`. The K3s setup playbook gives it the
  `sysadmin-services=true` label used by Harbor and Portainer.

The pinned stable Harbor release is scheduled to AMD64 because its complete
set of component images is not multi-architecture. The registry can still
store images for ARM64, AMD64, and other platforms.

### 2. Configure hostnames and initial credentials

Update the repository's `etc/sysadmin-env` with the values for this cluster:

```bash
export RANCHER_HOSTNAME="rancher.10.42.0.31.sslip.io"
export RANCHER_BOOTSTRAP_PASSWORD='replace-with-a-strong-password'
export HARBOR_HOSTNAME="harbor.10.42.0.31.sslip.io"
export HARBOR_ADMIN_PASSWORD='replace-with-a-strong-password'
export PORTAINER_HOSTNAME="portainer.10.42.0.31.sslip.io"
```

`HARBOR_ADMIN_PASSWORD` is the initial password for Harbor's built-in `admin`
account. `RANCHER_BOOTSTRAP_PASSWORD` is Rancher's first-login password. Change
both passwords in their respective interfaces after initial setup; changing
these environment variables later does not reset an existing installation.

Portainer prompts for its initial administrator account when first opened.
Afterward, create a Portainer API key and store it as `PORTAINER_API_KEY` in
`etc/sysadmin-env` for the repository's user-management scripts.

### 3. Deploy the services

Install the configuration with root-only permissions, then run the apply script:

```bash
sudo install -D -o root -g root -m 600 \
  ./etc/sysadmin-env /etc/k3s-turing-pi/sysadmin-env
sudo ./scripts/apply-sysadmin-services
```

The administration scripts read `/etc/k3s-turing-pi/sysadmin-env`
automatically. Whenever a value changes in the repository's `etc/sysadmin-env`,
rerun the `install` command to replace the installed copy, then rerun the
affected administration command.

Use this script instead of `kubectl apply -k`. Kubernetes does not expand the
environment-variable placeholders in the committed manifests, so the script
validates, renders, and replaces them in memory before applying the resources.
For an existing Harbor installation, the script also waits up to 30 minutes
for PostgreSQL to become ready before updating the Helm chart. This keeps the
pre-upgrade database migration job from starting while PostgreSQL is still
recovering. The script streams the database Pod logs during this wait.
It also prints the StatefulSet's ready-replica count every 10 seconds so the
gap between PostgreSQL startup messages and Kubernetes readiness is visible.

### 4. Check the deployment

Inspect the Helm installations and Pods:

```bash
sudo k3s kubectl get helmcharts -n kube-system
sudo k3s kubectl get pods -n sysadmin-system
sudo k3s kubectl get pods -n cattle-system
sudo k3s kubectl get pods -n cert-manager
sudo k3s kubectl get pods -n nvidia-device-plugin
```

Harbor consists of several Pods and can take longer than Portainer to become
ready. If a Harbor Pod remains pending, verify that the selected sysadmin node
has both the `sysadmin-services=true` and `kubernetes.io/arch=amd64` labels.
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

### 5. Trust the private ingress certificates locally

After all three ingresses are available, discover their private certificate
authorities and install them on the Ansible control machine:

```bash
sudo ./scripts/trust-k3s-crets
```

Harbor's official chart generates its ingress certificate automatically. The
trust script discovers that certificate through the Ingress and its TLS Secret.

### 6. Trust the private CAs on every K3s node

Distribute the discovered CAs to every K3s server and agent, then restart their
K3s services so containerd reloads the system trust store:

```bash
cd ansible
ansible-playbook -i inventory.yml trust-k3s-certs.yml
cd ..
```

Every node must be able to resolve `HARBOR_HOSTNAME` to the cluster's Traefik
ingress before it can pull images from the registry.

### 7. Open the services

- Harbor: `https://<HARBOR_HOSTNAME>`
- Portainer: `https://<PORTAINER_HOSTNAME>`
- Rancher: `https://<RANCHER_HOSTNAME>`

If your computer cannot reach the cluster network directly, follow the
[SSH tunneling guide](../docs/TUNNELING.md).

For Harbor's initial setup, log in as `admin` with
`HARBOR_ADMIN_PASSWORD`. For Rancher, log in as `admin` with
`RANCHER_BOOTSTRAP_PASSWORD`. Portainer guides you through creation of its
initial administrator account.

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
sudo k3s kubectl delete pod harbor-database-0 -n sysadmin-system
sudo k3s kubectl get pods -n sysadmin-system --watch
```

Setting `kernel.apparmor_restrict_unprivileged_unconfined=0` relaxes one Ubuntu
AppArmor hardening control; it does not disable AppArmor entirely. Remove the
override and restore the value to `1` after installing a fixed kernel, then
recreate affected Pods. A detailed reproduction and explanation of the same
container signal-denial behavior is available in this
[AppArmor regression investigation](https://homelab2.e-whisper.com/how-to-guides/troubleshooting/apparmor-signal-denied/).

## Deployment Reference

### Namespace layout

- Harbor: `sysadmin-system`
- Portainer: `sysadmin-system`
- Rancher: `cattle-system`
- cert-manager: `cert-manager`
- NVIDIA device plugin and Node Feature Discovery: `nvidia-device-plugin`

Rancher remains in `cattle-system` because some Rancher components assume that
namespace. cert-manager remains in its conventional `cert-manager` namespace
because it is a singleton cluster dependency with CRDs, webhooks, and
cluster-scoped RBAC. The NVIDIA device plugin remains in its own namespace
because it is a cluster-level hardware discovery service.

All five `HelmChart` resources use this label so they remain logically grouped:

```yaml
app.kubernetes.io/part-of: sysadmin-system
```

### Pinned versions

- Harbor: 2.15.4 (chart 1.19.4)
- Portainer CE: 2.45.2 (chart 245.2.0)
- Rancher: 2.15.0 (chart 2.15.1)
- cert-manager: v1.21.2
- NVIDIA device plugin: 0.19.3

Harbor and Portainer use persistent `local-path` volumes. Their data remains on
the selected sysadmin-service node, so back up the corresponding PVC data
before replacing or reprovisioning that node.

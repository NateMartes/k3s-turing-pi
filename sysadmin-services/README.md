# Sysadmin Services

This Kustomize bundle deploys Rancher, Harbor, Portainer, and cert-manager to
the K3s cluster. Run the commands below from the repository root.

## Getting Started

### 1. Check the prerequisites

Before deploying, ensure that:

- K3s is running and `kubectl` can reach the cluster.
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
recovering.

### 4. Check the deployment

Inspect the Helm installations and Pods:

```bash
sudo k3s kubectl get helmcharts -n kube-system
sudo k3s kubectl get pods -n sysadmin-system
sudo k3s kubectl get pods -n cattle-system
sudo k3s kubectl get pods -n cert-manager
```

Harbor consists of several Pods and can take longer than Portainer to become
ready. If a Harbor Pod remains pending, verify that the selected sysadmin node
has both the `sysadmin-services=true` and `kubernetes.io/arch=amd64` labels.

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

## Deployment Reference

### Namespace layout

- Harbor: `sysadmin-system`
- Portainer: `sysadmin-system`
- Rancher: `cattle-system`
- cert-manager: `cert-manager`

Rancher remains in `cattle-system` because some Rancher components assume that
namespace. cert-manager remains in its conventional `cert-manager` namespace
because it is a singleton cluster dependency with CRDs, webhooks, and
cluster-scoped RBAC.

All four `HelmChart` resources use this label so they remain logically grouped:

```yaml
app.kubernetes.io/part-of: sysadmin-system
```

### Pinned versions

- Harbor: 2.15.4 (chart 1.19.4)
- Portainer CE: 2.45.2 (chart 245.2.0)
- Rancher: 2.15.0 (chart 2.15.1)
- cert-manager: v1.21.2

Harbor and Portainer use persistent `local-path` volumes. Their data remains on
the selected sysadmin-service node, so back up the corresponding PVC data
before replacing or reprovisioning that node.

# sysadmin-system

Kustomize bundle for system-admin services running on the K3s cluster.

## Namespace layout

`sysadmin-system` is the namespace for admin services that safely support a
custom namespace.

- Portainer: `sysadmin-system`
- Rancher: `cattle-system`
- cert-manager: `cert-manager`

Rancher is intentionally left in `cattle-system`. Rancher has components that
assume this namespace, so moving it to `sysadmin-system` is not a safe
deployment choice. cert-manager is intentionally left in
its conventional `cert-manager` namespace because it is a singleton
cluster-level dependency with CRDs, webhooks, and cluster-scoped RBAC.

All three HelmChart resources are labeled:

```yaml
app.kubernetes.io/part-of: sysadmin-system
```

so the manifests remain logically grouped as one system bundle.

## Versions

- Rancher: 2.15.0
- Portainer CE: 245.2.0
- cert-manager: v1.21.2

Chart and application versions are pinned.

## Before applying

Set both service hostnames in `sysadmin-env`:

```bash
export RANCHER_HOSTNAME="rancher.10.42.0.31.sslip.io"
export PORTAINER_HOSTNAME="portainer.10.42.0.31.sslip.io"
```

Each hostname must resolve to a K3s node. The committed manifests contain
environment-variable placeholders, which the apply script replaces in memory.

## Apply

```bash
source ./sysadmin-env
sudo -E ./scripts/apply-sysadmin-services
```

Use the apply script instead of `kubectl apply -k`; Kubernetes does not expand
shell environment variables in YAML manifests.

## Check

```bash
sudo -E k3s kubectl get pods -n sysadmin-system
sudo -E k3s kubectl get pods -n cattle-system
sudo -E k3s kubectl get pods -n cert-manager
sudo -E k3s kubectl get helmcharts -n kube-system
```

## Access

Portainer:

```text
https://<PORTAINER_HOSTNAME>
```

Rancher:

```text
https://<RANCHER_HOSTNAME>
```

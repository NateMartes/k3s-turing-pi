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

Edit `rancher.yaml`:

```yaml
hostname: rancher.local
```

and replace it with a hostname that resolves to a K3s node.

Example:

```yaml
hostname: rancher.192.168.1.50.sslip.io
```

Edit `portainer.yaml`:
```yaml
host: portainer.192.168.1.50.sslip.io
```
and replace it with a hostname that resolves to a K3s node.

## Apply

```bash
sudo kubectl apply -k ./sysadmin-system
```

## Check

```bash
sudo k3s kubectl get pods -n sysadmin-system
sudo k3s kubectl get pods -n cattle-system
sudo k3s kubectl get pods -n cert-manager
sudo k3s kubectl get helmcharts -n kube-system
```

## Access

Portainer:

```text
https://<hostname configured in portainer.yaml>
```

Rancher:

```text
https://<hostname configured in rancher.yaml>
```

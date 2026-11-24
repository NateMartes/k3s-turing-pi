# Jihwija plumbing

Every operation behind the `jihwija` command is also an executable script in
`scripts/plumbing-scripts`. The CLI adds discoverable verb-first routing but
does not hide or reimplement maintenance behavior.

## Cluster plumbing

| Script | Purpose |
| --- | --- |
| `init-cluster.py` | Normalize an Ansible inventory and configure cluster variables. |
| `install-k3s.py` | Run the K3s setup playbook, discover and taint GPU nodes, and show nodes. |
| `uninstall-k3s.py` | Confirm and remove K3s from every inventory node. |
| `add-node.py` | Validate, inventory, and provision a worker node. |
| `remove-node.py` | Drain, uninstall, delete, and uninventory a worker node. |
| `set-secret.py` | Safely update one known protected configuration value. |
| `set-hostname.py` | Configure and optionally redeploy one service hostname. |
| `deploy-services.py` | Render, apply, wait for, and report service deployments. |
| `trust-k3s-certs.py` | Install and distribute service certificate trust. |
| `enable-quotas.py` | Enable user quotas on the filesystem containing a path. |
| `disable-quotas.py` | Disable user quotas while preserving quota metadata. |

## User plumbing

`create-user.py`, `remove-user.py`, `change-user-password.py`, `change-user-quota.py`,
`grant-user-privilege.py`, and `revoke-user-privilege.py` coordinate user accounts,
component resources, and allowlisted elevated access. Quota enable/disable
commands, GPU taint commands, and every component installer/uninstaller live
in the same directory.

Examples:

```bash
sudo ./scripts/plumbing-scripts/create-user.py bob --no-quota
sudo ./scripts/plumbing-scripts/change-user-quota.py bob --linux-quota 10GB
sudo ./scripts/plumbing-scripts/change-user-password.py bob
sudo ./scripts/plumbing-scripts/remove-user.py bob --yes
sudo ./scripts/plumbing-scripts/grant-user-privilege.py bob argo-template-admin
sudo ./scripts/plumbing-scripts/revoke-user-privilege.py bob argo-template-admin
sudo ./scripts/plumbing-scripts/add-node.py worker-04 10.42.0.40 --group workers
```

Run any script with `--help` for its complete interface. Scripts that manage
system accounts, protected configuration, or Kubernetes require root. Ansible
commands preserve the invoking operator's SSH identity when entered through
`sudo`.

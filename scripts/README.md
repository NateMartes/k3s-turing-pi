# Jihwija plumbing

Every operation behind the `jihwija` command is also an executable script in
`scripts/plumbing-scripts`. The CLI adds discoverable verb-first routing but
does not hide or reimplement maintenance behavior.

## Cluster plumbing

| Script | Purpose |
| --- | --- |
| `init-cluster` | Normalize an Ansible inventory and configure cluster variables. |
| `install-k3s` | Run the K3s setup playbook, discover and taint GPU nodes, and show nodes. |
| `uninstall-k3s` | Confirm and remove K3s from every inventory node. |
| `add-node` | Validate, inventory, and provision a worker node. |
| `remove-node` | Drain, uninstall, delete, and uninventory a worker node. |
| `set-secret` | Safely update one known protected configuration value. |
| `set-hostname` | Configure and optionally redeploy one service hostname. |
| `deploy-services` | Render, apply, wait for, and report service deployments. |
| `trust-k3s-certs` | Install and distribute service certificate trust. |
| `enable-quotas` | Enable user quotas on the filesystem containing a path. |
| `disable-quotas` | Disable user quotas while preserving quota metadata. |

## User plumbing

`create-user`, `remove-user`, `change-user-password`, and `change-user-quota`
coordinate the component-level account scripts. Quota enable/disable commands,
GPU taint commands, and every component installer/uninstaller live in the same
directory.

Examples:

```bash
sudo ./scripts/plumbing-scripts/create-user bob --no-quota
sudo ./scripts/plumbing-scripts/change-user-quota bob --linux-quota 10GB
sudo ./scripts/plumbing-scripts/change-user-password bob
sudo ./scripts/plumbing-scripts/remove-user bob --yes
sudo ./scripts/plumbing-scripts/add-node worker-04 10.42.0.40 --group workers
```

Run any script with `--help` for its complete interface. Scripts that manage
system accounts, protected configuration, or Kubernetes require root. Ansible
commands preserve the invoking operator's SSH identity when entered through
`sudo`.

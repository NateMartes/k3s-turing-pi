# Plumbing Scripts

This directory is the complete operational layer used by the `jihwija` CLI.
Every cluster, node, service, and user operation remains directly executable
here for maintainers. The friendly CLI routes arguments to these scripts
without reimplementing their behavior.

Shared Python modules live in `lib/`; the plumbing root intentionally contains
only directly executable commands, requirements, and this documentation.

Passwords for Rancher/Portainer creation and updates may be supplied through
`USER_PASSWORD` so orchestration does not expose the user's password in process
arguments.

Administrative credentials should use:

- `HARBOR_ADMIN_PASSWORD` (and optionally `HARBOR_ADMIN_USERNAME`, which defaults to `admin`)
- `RANCHER_TOKEN`
- `RANCHER_CLUSTER_ID`
- `PORTAINER_API_KEY`

Service hostnames must be configured with:

- `RANCHER_HOSTNAME`
- `HARBOR_HOSTNAME`
- `PORTAINER_HOSTNAME`

If a variable is not set, the relevant command exits with an error unless an
explicit `-H`/`--hostname` argument is provided.

## Argo workflow runner

Install the Argo executor identity with namespace `admin` access and the user's
read-only access to shared cluster workflow templates after creating the
user's K3s namespace:

```bash
sudo ./install-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

Remove the runner resources and the user's cluster template reader binding
with:

```bash
sudo ./uninstall-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

The main `create-user` and `remove-user` commands call these automatically.

## User kubeconfig selection

The Jihwija installer installs the kubeconfig profile. `set-hostname argo`
renders and installs the Argo profile with the configured endpoint. Maintainers
performing a manual source-tree setup can install them after replacing the
`@ARGO_HOSTNAME@` placeholder:

```bash
sudo install -D -o root -g root -m 644 \
  ../../etc/profile.d/jihwija-kubeconfig.sh \
  /etc/profile.d/jihwija-kubeconfig.sh
sudo install -D -o root -g root -m 644 \
  ../../etc/profile.d/jihwija-argo-variables.sh \
  /etc/profile.d/jihwija-argo-variables.sh
```

For users with a readable `~/.kube/config`, login shells then set `KUBECONFIG`
to that file instead of allowing the K3s-provided `kubectl` command to fall
back to the restricted cluster administrator config at
`/etc/rancher/k3s/k3s.yaml`.

The profile script does not modify individual `.bashrc` or `.profile` files and
does not override an explicitly set `KUBECONFIG`. Existing sessions must log
out and back in after the script is first installed.

The Argo profile sets `ARGO_SERVER` to the cluster's Argo Workflows endpoint
and derives `ARGO_TOKEN` from the active user in the user's kubeconfig. It does
not override either variable when it is already set. The profile takes effect
on the user's next login.

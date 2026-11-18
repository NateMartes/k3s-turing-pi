# Plumbing Scripts

These are lower-level commands used by the main user-management scripts.

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

Install the namespace-scoped Argo executor identity, temporary Service
permissions, and the user's read-only access to shared cluster workflow
templates after creating the user's K3s namespace:

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

Before running `create-user` for the first time, install the repository's
system-wide profile scripts:

```bash
sudo install -D -o root -g root -m 644 \
  ../../etc/profile.d/k3s-turing-pi-kubeconfig.sh \
  /etc/profile.d/k3s-turing-pi-kubeconfig.sh
sudo install -D -o root -g root -m 644 \
  ../../etc/profile.d/k3s-turing-pi-argo-server.sh \
  /etc/profile.d/k3s-turing-pi-argo-server.sh
```

For users with a readable `~/.kube/config`, login shells then set `KUBECONFIG`
to that file instead of allowing the K3s-provided `kubectl` command to fall
back to the restricted cluster administrator config at
`/etc/rancher/k3s/k3s.yaml`.

The profile script does not modify individual `.bashrc` or `.profile` files and
does not override an explicitly set `KUBECONFIG`. Existing sessions must log
out and back in after the script is first installed.

The Argo profile sets `ARGO_SERVER` to the cluster's Argo Workflows endpoint
unless the user has already selected another endpoint. It also takes effect on
the user's next login.

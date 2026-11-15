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

Install the namespace-scoped Argo executor identity after creating the user's
K3s namespace:

```bash
sudo ./install-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

Remove only those runner resources with:

```bash
sudo ./uninstall-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

The main `create-user` and `remove-user` commands call these automatically.

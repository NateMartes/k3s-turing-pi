# Plumbing Scripts

These are lower-level commands used by the main user-management scripts.

Passwords for Rancher/Portainer creation and updates may be supplied through
`USER_PASSWORD` so orchestration does not expose the user's password in process
arguments.

Administrative credentials should use:

- `RANCHER_TOKEN`
- `RANCHER_CLUSTER_ID`
- `PORTAINER_API_KEY`

Service hostnames must be configured with:

- `RANCHER_HOSTNAME`
- `PORTAINER_HOSTNAME`

If a variable is not set, the relevant command exits with an error unless an
explicit `-H`/`--hostname` argument is provided.

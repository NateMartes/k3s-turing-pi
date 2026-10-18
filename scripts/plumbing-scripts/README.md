# Plumbing Scripts

These are lower-level commands used by the main user-management scripts.

The old typo alias `uinstall-k3s-namespace` is intentionally not included.

Passwords for Rancher/Portainer creation and updates may be supplied through
`USER_PASSWORD` so orchestration does not expose the user's password in process
arguments.

Administrative credentials should use:
- `RANCHER_TOKEN`
- `RANCHER_CLUSTER_ID`
- `PORTAINER_API_KEY`

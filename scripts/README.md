# Scripts

This repository contains two layers of administration tools:

- **`user-scripts/`** — the main commands an administrator normally uses.
- **`plumbing-scripts/`** — lower-level commands used by the main commands to
  configure Docker, Portainer, K3s, and Rancher.

Per-user state is stored locally beside the main scripts:

```text
user-scripts/state/<username>.json
```

## Main Commands

### `trust-k3s-certs`

When run, adds the current K3s services' certificates to the Linux trust
store and the Chromium trust store as well. This is nice for removing warnings for local
clusters when proper DNS is not set up yet.

```bash
sudo -E ./trust-k3s-certs
```

### `create-user`

Creates a complete managed user.

- Uses the same password for:
  - Linux
  - Rancher
  - Portainer
- Applies the requested filesystem quota.
- Installs rootless Docker for the user.
- Starts a Portainer Agent connected to that user's rootless Docker socket.
- Creates `<username>-namespace` in K3s.
- Creates the user's Rancher account and project.
- Adds the user's namespace to the Rancher project.
- Creates the user's Portainer account.
- Registers the user's Portainer Agent environment.
- Prints all created resources and the generated password.

```bash
sudo -E ./user-scripts/create-user -u bob -q 5GB
```

Quota may be specified as MB or GB:

### `remove-user`

Removes a managed user's resources.

It removes, in reverse provisioning order:

- Portainer account and environment
- Rancher project and Rancher account
- K3s namespace and namespace resources
- Portainer Agent
- Rootless Docker
- Linux account

By default, the user's home directory is preserved.

```bash
sudo -E ./user-scripts/remove-user -u bob
```

To also delete the home directory and Docker data:

```bash
sudo -E ./user-scripts/remove-user -u bob --purge-data
```

For non-interactive removal:

```bash
sudo -E ./user-scripts/remove-user -u bob --yes
```

### `change-user-password`

Changes the password everywhere the user has a password-based account.

Prompts for the new password twice and updates:

- Rancher
- Portainer
- Linux

The password is not echoed to the terminal.

Linux is updated last so that a failed Rancher or Portainer update does not
knowingly leave Linux on a different password.

```bash
sudo -E ./user-scripts/change-user-password -u bob
```

### `enable-quotas`

Turns quotas on for a specific directory on the Linux filesystem.

```bash
sudo ./enable-quotas /home
```

### `disable-quotas`

Turns quotas off for a specific directory on the Linux filesystem.

```bash
sudo ./disable-quotas /home
```

### `change-user-quota`

Changes the Linux filesystem quota for a managed user.

- Finds the filesystem containing the user's home directory.
- Applies the requested user quota using `setquota`.
- Updates the user's local state file.

```bash
sudo ./user-scripts/change-user-quota 10GB -u bob
```

```bash
sudo ./user-scripts/change-user-quota 500MB -u bob
```

## Plumbing Commands

These commands are normally called automatically by the main user scripts.

### `install-docker-rootless`

Installs and configures rootless Docker for a Linux user.

```bash
sudo ./plumbing-scripts/install-docker-rootless -u bob
```

### `uninstall-docker-rootless`

Removes the user's rootless Docker service.

```bash
sudo ./plumbing-scripts/uninstall-docker-rootless -u bob
```

To remove Docker data too:

```bash
sudo ./plumbing-scripts/uninstall-docker-rootless -u bob --purge-data
```

### `install-portainer-agent`

Runs a Portainer Agent against the user's rootless Docker socket.

```bash
sudo -E ./plumbing-scripts/install-portainer-agent \
  -u bob \
  -H portainer.10.42.0.31.sslip.io \
  --port 9002
```

Each user on the same machine needs a unique agent port.

### `uninstall-portainer-agent`

Removes the user's Portainer Agent container.

```bash
sudo ./plumbing-scripts/uninstall-portainer-agent -u bob
```

### `install-k3s-namespace`

Creates `<username>-namespace`, a service account, RBAC, and the user's kubeconfig.

```bash
sudo -E ./plumbing-scripts/install-k3s-namespace -u bob
```

### `uninstall-k3s-namespace`

Deletes the user's namespace and the kubeconfig created by this tool.

```bash
sudo -E ./plumbing-scripts/uninstall-k3s-namespace -u bob
```

Deleting the namespace also deletes namespaced Kubernetes resources inside it.

### `install-rancher-account`

Creates a Rancher user and project and assigns the user's namespace to that project.

```bash
sudo -E ./plumbing-scripts/install-rancher-account \
  -u bob \
  --cluster-id local
```

The default Rancher host is:

```text
rancher.10.42.0.31.sslip.io
```

### `uninstall-rancher-account`

Deletes the user's Rancher project and Rancher account.

```bash
sudo -E ./plumbing-scripts/uninstall-rancher-account \
  -u bob \
  --cluster-id local
```

### `set-rancher-password`

Updates an existing Rancher user's password.

Normally called by `change-user-password`.

```bash
sudo -E ./plumbing-scripts/set-rancher-password -u bob
```

### `install-portainer-account`

Creates a Portainer account and registers the user's Agent environment.

```bash
sudo -E ./plumbing-scripts/install-portainer-account \
  -u bob \
  --agent-address node1.example.internal:9002
```

### `uninstall-portainer-account`

Deletes the user's Portainer environment and Portainer account.

```bash
sudo -E ./plumbing-scripts/uninstall-portainer-account -u bob
```

## Dependencies

These tools are intended for Debian/Ubuntu systems.

Install the common operating-system dependencies with:

```bash
sudo apt update
sudo apt install -y \
  python3 \
  python3-requests \
  sudo \
  curl \
  uidmap \
  dbus-user-session \
  slirp4netns \
  fuse-overlayfs \
  quota
```

The scripts also require:

- `systemd`
- `loginctl`
- `findmnt`
- `setquota`
- `useradd`
- `userdel`
- `chpasswd`
- `kubectl`
- a working K3s installation for Kubernetes namespace management
- a reachable Rancher installation for Rancher commands
- a reachable Portainer installation for Portainer commands

Rootless Docker installation also requires valid subordinate UID/GID ranges in:

```text
/etc/subuid
/etc/subgid
```

The Docker installer attempts to configure these when run as root.

## Quota Configuration

Installing the `quota` package alone is not enough.

The filesystem containing the users' home directories must have user quotas
enabled, typically with the `usrquota` mount option.

For example, if `/home` is on `/dev/sda2`, its `/etc/fstab` entry may need something like:

```text
UUID=... /home ext4 defaults,usrquota 0 2
```

After enabling quotas, the filesystem may need to be remounted and quota metadata
initialized before `setquota` can work.

## Authentication Environment Variables

For administrator operations, use environment variables rather than putting
sensitive administrator credentials directly in shell history.

### Rancher

```bash
export RANCHER_TOKEN='token-xxxxx:yyyyyyyy'
export RANCHER_CLUSTER_ID='local'
export RANCHER_HOSTNAME='rancher.10.42.0.31.sslip.io'
```

### Portainer

```bash
export PORTAINER_API_KEY='ptr_xxxxxxxxx'
export PORTAINER_HOSTNAME='portainer.10.42.0.31.sslip.io'
```

The hostname variables are required by both the main user commands and the
plumbing scripts. Explicit hostname command-line options still take precedence;
commands that have neither a configured variable nor an explicit/stored
hostname exit with an error.

Then preserve those environment variables through `sudo`:

```bash
sudo -E ./user-scripts/create-user -u bob -q 5GB
```

## State Files

State files are stored at:

```text
user-scripts/state/<username>.json
```

Example:

```text
user-scripts/state/bob.json
```

They record resource information such as:

- Linux username and home directory
- quota
- K3s namespace
- Rancher project
- Portainer environment
- Portainer Agent port and address
- Rancher and Portainer hostnames

They do **not** contain passwords.

## Permissions

All command files in `user-scripts/` and `plumbing-scripts/` are marked executable.

You can run them directly:

```bash
sudo -E ./user-scripts/create-user -u bob -q 5GB
```

or install/symlink the main commands into `/usr/local/bin`.

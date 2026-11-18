# Scripts

This repository contains two layers of administration tools:

- **`user-scripts/`** — the main commands an administrator normally uses.
- **`plumbing-scripts/`** — lower-level commands used by the main commands to
  configure Docker, Portainer, K3s, Harbor, and Rancher.

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
sudo ./trust-k3s-crets
```

### `create-user`

Creates a complete managed user.

- Uses the generated password for Harbor, Rancher, Portainer, and Linux
  accounts created by the script. Pre-existing Linux account passwords remain
  unchanged.
- Applies the requested filesystem, K3s, and Harbor quotas unless `--no-quota`
  is set.
- Prompts for K3s namespace CPU, memory, storage, and NVIDIA GPU quotas
  (defaults: 2 CPU, 6Gi memory, 10Gi storage, and 1 GPU) unless `--no-quota`
  is set.
- Installs rootless Docker and the Docker Compose CLI plugin for the user.
- Starts a Portainer Agent connected to that user's rootless Docker socket.
- Creates `<username>-namespace` in K3s.
- Installs `argo-workflow-runner`, its executor and temporary Service RBAC, and
  read-only shared Argo workflow template access for the user.
- Creates the user's Harbor account and private `<username>-namespace` project
  with a 10GiB storage quota unless `--no-quota` is set.
- Creates the user's Rancher account and project.
- Adds the user's namespace to the Rancher project.
- Creates the user's Portainer account.
- Registers the user's Portainer Agent environment.
- Prints all created resources followed by grouped login details for
  Linux/rootless Docker, K3s, Argo Workflows, Harbor, Rancher, and Portainer.

Before creating the first user, install the system-wide kubeconfig profile from
the repository root. This is a one-time host setup step:

```bash
sudo install -D -o root -g root -m 644 \
  ./etc/profile.d/k3s-turing-pi-kubeconfig.sh \
  /etc/profile.d/k3s-turing-pi-kubeconfig.sh
```

Then create the user:

```bash
sudo ./scripts/create-user -u bob -q 5GB
```

If the Linux account already exists, `create-user` reuses it instead of
failing. Its password is left unchanged, and the state records that the account
was pre-existing so `remove-user` will preserve the account and home directory.

Use `--only` (or `-o`) with a comma-separated list to create resources only
for selected services or features:

```bash
sudo ./scripts/create-user -u sysadmin -q 5GB \
  --only harbor
```

The supported selections are `harbor`, `rancher`, `portainer`,
`portainer-agent`, `docker-rootless`, `argo-workflow-runner`, and
`k3s-namespace`. Selected services must include their dependencies: the
Portainer Agent requires rootless Docker, while the Argo runner and Rancher
namespace attachment require the K3s namespace.
When `--only` is omitted, the entire service list is selected.
Run `./scripts/create-user --help` for the full option description.

The final output contains each service's URL (where applicable), username,
password or token, and relevant project or namespace. Share it securely. The
K3s token is the same service-account token stored in the user's
`~/.kube/config` and in their namespace's `<username>-user-token` Secret;
`create-user` does not save another copy in its state file.

By default, each stage shows a rolling window containing the latest four raw
log lines. If a stage fails, its complete output is printed as a labeled log
block. To stream all command output without the rolling window, use
`--raw-logs`:

```bash
sudo ./user-scripts/create-user -u bob -q 5GB --raw-logs
```

The command prints one upfront warning listing services contacted over HTTPS
without certificate verification. Repetitive library-level unverified HTTPS
warnings are suppressed.

The K3s resource quotas can also be supplied non-interactively:

```bash
sudo ./user-scripts/create-user -u bob -q 5GB \
  --k3s-cpu-quota 2 --k3s-memory-quota 6Gi \
  --k3s-storage-quota 10Gi --k3s-gpu-quota 1
```

Quota may be specified as MB or GB:

```bash
sudo ./user-scripts/create-user -u bob -q 5GB
```

To create the user without prompting for or configuring any filesystem, K3s,
or Harbor quota:

```bash
sudo ./user-scripts/create-user -u bob --no-quota
```

### `remove-user`

Removes a managed user's resources.

It removes, in reverse provisioning order:

- Portainer account and environment
- Rancher project and Rancher account
- Harbor project and Harbor account
- Argo workflow runner RBAC
- K3s namespace and namespace resources
- Portainer Agent
- Rootless Docker
- Linux account

By default, the user's home directory is preserved.

```bash
sudo ./user-scripts/remove-user -u bob
```

Use `--only` (or `-o`) to remove resources only for selected services. Linux
account removal is unchanged:

```bash
sudo ./user-scripts/remove-user -u bob \
  --only harbor,rancher,portainer
```

The removal command accepts the same service list as `create-user`. When
`--only` is omitted, the entire service list is selected.
When unselected services remain, their state file is retained so they can be
removed by a later command.

To also delete the home directory and Docker data for an account created by
`create-user`:

```bash
sudo ./user-scripts/remove-user -u bob --purge-data
```

For non-interactive removal:

```bash
sudo ./user-scripts/remove-user -u bob --yes
```

Removal uses the same compact status display and supports `--raw-logs` for
unfiltered command output.

### `change-user-password`

Changes the password everywhere the user has a password-based account.

Prompts for the new password twice and updates:

- Rancher
- Harbor
- Portainer
- Linux

The password is not echoed to the terminal.

Passwords must be at least 15 characters long and contain at least one
uppercase letter. Passwords generated by `create-user` always meet this policy.
Generated-password settings live in `password_setup.py`, including the 180-word
dictionary, symbol set, and minimum password length. Every configured word is
alphabetic, title-cased, and at least seven characters long.

Linux is updated last so that a failed Harbor, Rancher, or Portainer update does not
knowingly leave Linux on a different password.

```bash
sudo ./user-scripts/change-user-password -u bob
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

Prompts for every managed quota, using the current stored values as defaults:

- Linux filesystem storage
- K3s CPU, memory, storage, and NVIDIA GPUs
- Harbor project storage

It updates each service and records successful changes in the user's state
file. The legacy positional value still sets the Linux quota, while the other
values are prompted.

```bash
sudo ./user-scripts/change-user-quota 10GB -u bob
```

```bash
sudo ./user-scripts/change-user-quota 500MB -u bob
```

For a fully non-interactive update:

```bash
sudo ./user-scripts/change-user-quota -u bob \
  --linux-quota 10GB \
  --k3s-cpu-quota 4 \
  --k3s-memory-quota 12Gi \
  --k3s-storage-quota 20Gi \
  --k3s-gpu-quota 1 \
  --harbor-storage-quota 20GB
```

Use `--raw-logs` to stream the K3s and Harbor command output.

## Plumbing Commands

These commands are normally called automatically by the main user scripts.

### `install-docker-rootless`

Installs and configures rootless Docker and the `docker compose` CLI plugin for
a Linux user. Compose is installed under the user's Docker CLI plugin directory
and is available through commands such as `docker compose up`.

On hosts where AppArmor blocks unprivileged user namespaces, it creates the
managed `/etc/sysctl.d/90-k3s-turing-pi-rootless-docker-apparmor.conf` override
required by rootless Docker. The override is reference-counted across managed
users and is removed (with the original restriction restored) when the final
managed rootless Docker user is removed.

```bash
sudo ./plumbing-scripts/install-docker-rootless -u bob
```

### `uninstall-docker-rootless`

Removes the user's rootless Docker service and the Docker Compose plugin
installed by this project. Pre-existing Compose installations are preserved.

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
sudo ./plumbing-scripts/install-portainer-agent \
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

Creates `<username>-namespace`, a service account, RBAC, a `ResourceQuota`, and
the user's kubeconfig. Defaults are 2 CPU, 6Gi memory, 10Gi storage, and 1
NVIDIA GPU across pod requests/limits; the storage quota also limits
persistent-volume requests.

```bash
sudo ./plumbing-scripts/install-k3s-namespace -u bob
```

Override a namespace's quotas when invoking the plumbing command directly:

```bash
sudo ./plumbing-scripts/install-k3s-namespace -u bob \
  --cpu-quota 4 --memory-quota 12Gi --storage-quota 20Gi --gpu-quota 1
```

Use `--no-quota` to create the namespace without a `ResourceQuota`:

```bash
sudo ./plumbing-scripts/install-k3s-namespace -u bob --no-quota
```

### `uninstall-k3s-namespace`

Deletes the user's namespace and the kubeconfig created by this tool.

```bash
sudo ./plumbing-scripts/uninstall-k3s-namespace -u bob
```

### `install-argo-workflow-runner`

Installs `argo-workflow-runner` with `WorkflowTaskResult` permissions and
create, get, and delete access to Services in an existing user namespace. It
also lets the user's namespace service account read shared
`ClusterWorkflowTemplate` resources for direct Argo CLI submission. Both the
user and namespace are explicit so the command cannot silently target
`default` or `argo`.

```bash
sudo ./plumbing-scripts/install-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

### `uninstall-argo-workflow-runner`

Removes the runner service account, Role, RoleBinding, and the user's cluster
template reader binding without deleting the namespace or other user
workloads.

```bash
sudo ./plumbing-scripts/uninstall-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

Deleting the namespace also deletes namespaced Kubernetes resources inside it.

### `set-k3s-quota`

Updates only the managed `ResourceQuota` in an existing user's namespace.

```bash
sudo ./plumbing-scripts/set-k3s-quota -u bob \
  --cpu-quota 4 --memory-quota 12Gi --storage-quota 20Gi --gpu-quota 1
```

### `k3s-taint-gpu-nodes` and `k3s-untaint-gpu-nodes`

Keeps ordinary workloads off nodes that advertise an allocatable
`nvidia.com/gpu` resource. The taint command discovers those nodes and applies
`nvidia.com/gpu=true:NoSchedule`:

```bash
sudo ./scripts/k3s-taint-gpu-nodes
```

GPU workloads must request a GPU and tolerate that taint:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: "true"
    effect: NoSchedule
```

Remove the managed GPU taint from every node that has it with:

```bash
sudo ./scripts/k3s-untaint-gpu-nodes
```

The untaint command discovers nodes by the taint rather than current GPU
availability, so it still works if the NVIDIA device plugin is temporarily
unavailable.

### `install-harbor-account`

Creates a local Harbor user and a private Harbor project named
`<username>-namespace`, matching the user's K3s namespace. The user receives
Project Admin access to only that project, so it can push and manage its own
registry artifacts without receiving Harbor-wide administrator access.

```bash
sudo ./plumbing-scripts/install-harbor-account -u bob
```

The user's password can be supplied through `USER_PASSWORD`; the Harbor
administrator password comes from `HARBOR_ADMIN_PASSWORD`. The command creates
database-authenticated Harbor users, so it is not applicable when Harbor is
configured to use LDAP, AD, or OIDC for user authentication.

Each managed Harbor namespace project receives a 10GiB (10,737,418,240-byte)
storage quota by default. Use `--storage-quota-bytes` to override it, or use
`--no-quota` to skip Harbor quota configuration.

### `set-harbor-quota`

Updates only an existing managed Harbor project's storage quota.

```bash
sudo ./plumbing-scripts/set-harbor-quota -u bob \
  --storage-quota-bytes 21474836480
```

### `uninstall-harbor-account`

Deletes the user's `<username>-namespace` Harbor project, including all of its
registry artifacts, then deletes the local Harbor user.

```bash
sudo ./plumbing-scripts/uninstall-harbor-account -u bob
```

To retain the project and its artifacts while deleting only the user:

```bash
sudo ./plumbing-scripts/uninstall-harbor-account -u bob --keep-project
```

### `install-rancher-account`

Creates a Rancher user and project and assigns the user's namespace to that project.

```bash
sudo ./plumbing-scripts/install-rancher-account \
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
sudo ./plumbing-scripts/uninstall-rancher-account \
  -u bob \
  --cluster-id local
```

### `set-rancher-password`

Updates an existing Rancher user's password.

Normally called by `change-user-password`.

```bash
sudo ./plumbing-scripts/set-rancher-password -u bob
```

### `set-harbor-password`

Updates a database-authenticated Harbor user's password using the Harbor
administrator API.

```bash
sudo ./plumbing-scripts/set-harbor-password -u bob
```

### `install-portainer-account`

Creates a Portainer account and registers the user's Agent environment.

```bash
sudo ./plumbing-scripts/install-portainer-account \
  -u bob \
  --agent-address node1.example.internal:9002
```

### `uninstall-portainer-account`

Deletes the user's Portainer environment and Portainer account.

```bash
sudo ./plumbing-scripts/uninstall-portainer-account -u bob
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
- a reachable Harbor installation using database authentication for Harbor commands

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

## Administrator configuration

Administrator operations read hostnames and credentials from
`/etc/k3s-turing-pi/sysadmin-env`. From the repository root, install the
configured file with root-only permissions before running these commands:

```bash
sudo install -D -o root -g root -m 600 \
  ./etc/sysadmin-env /etc/k3s-turing-pi/sysadmin-env
```

The hostname variables are required by both the main user commands and the
plumbing scripts. Explicit hostname command-line options still take precedence;
commands that have neither a configured variable nor an explicit/stored
hostname exit with an error.

The same file stores `ARGO_HOSTNAME` for the administrator-managed Argo
Workflows Ingress. The user-management commands do not require that value.

Whenever a value changes, update the repository's `etc/sysadmin-env` and rerun the
`install` command above. The next administration command will read the new
values from the installed file.

Then run the command normally through `sudo`:

```bash
sudo ./user-scripts/create-user -u bob -q 5GB
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
- K3s CPU, memory, storage, and GPU quotas
- Harbor project and storage quota
- Rancher project
- Portainer environment
- Portainer Agent port and address
- Harbor, Rancher, and Portainer hostnames

They do **not** contain passwords.

## Permissions

All administrator command files are marked executable.

You can run them directly:

```bash
sudo ./user-scripts/create-user -u bob -q 5GB
```

or install/symlink the main commands into `/usr/local/bin`.

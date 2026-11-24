---
title: JIHWIJA-SETUP
section: 7
header: Jihwija Manual
footer: Jihwija 0.1.0
man-name: jihwija-setup
description: install and configure a Jihwija cluster
---

# Cluster Setup Guide: Jihwija CLI & Manual Native Pipelines

This guide provides complete instructions for setting up and operating the Turing Pi K3s cluster. You can provision and conduct your cluster using either:

1. **Option A: Guided Automated Setup (Jihwija CLI)** — A streamlined CLI overlay (`jihwija`) that handles validation, inventory generation, credential storage, deployment, and user provisioning.
2. **Option B: Manual Native Setup (The "OG" Pipeline)** — The original, direct operational workflow running Ansible playbooks, plumbing scripts, and Kubernetes manifests step-by-step.

Both approaches configure the identical underlying infrastructure: a native single-server K3s cluster, Traefik ingress, Rancher, Harbor registry, Portainer, Argo Workflows, cert-manager, NVIDIA GPU support, and multi-tenant user isolation.

---

## Prerequisites (Common to Both Options)

### 1. Hardware & OS
- **OS:** Ubuntu Linux (Ubuntu 22.04, 24.04, or 26.04 LTS recommended) on all nodes.
- **Architecture:** 
  - Turing Pi 2 board or heterogeneous network of RK1 / Jetson Orin / Raspberry Pi / x86 machines.
  - **Harbor Registry Requirement:** At least one node in your cluster **must be AMD64 (x86_64)** to run the Harbor registry stack. Harbor can store multi-architecture images (ARM64, AMD64, etc.), but its core backend services require AMD64.
- Follow the node-specific hardware guides if preparing hardware:
  - [Adding a new node (RK1 / Raspberry Pi)](ADDING_A_NEW_NODE.md)
  - [Adding a Jetson Orin](ADDING_A_JETSON_ORIN.md)

### 2. Network Layout
Ensure your IP subnets do not overlap:
- **Host LAN CIDR:** e.g., `10.42.0.0/24`
- **K3s Pod CIDR:** e.g., `10.244.0.0/16`
- **K3s Service CIDR:** e.g., `10.43.0.0/16`

### 3. SSH Connectivity
The controller / management machine must have passwordless SSH key access and `sudo` rights on every cluster node:

```bash
ssh-keygen -t ed25519
ssh-copy-id <ssh_user>@<node_ip>
```

Verify that you can SSH into every node without a password prompt.

---

## Option A: Guided Setup with the Jihwija CLI

The Jihwija CLI (`jihwija`) wraps the underlying Ansible playbooks and plumbing scripts into a discoverable command structure.

### 1. Install Jihwija on the Controller / K3s Server Node

Run the installer on the Ubuntu host designated as the K3s server:

```bash
git clone https://github.com/NateMartes/k3s-turing-pi.git
cd k3s-turing-pi
sudo ./install.sh
```

This installs system dependencies, copies the installation to `/opt/jihwija`, sets up a dedicated virtual environment, installs `/usr/local/bin/jihwija`, and establishes permissions.

### 2. Initialize the Cluster Inventory

Initialize your cluster settings from the sample inventory:

```bash
sudo jihwija init ansible/inventory.example.yml
```

The interactive initializer will prompt for:
- Default SSH operator account.
- K3s version (e.g. `v1.36.1+k3s1`).
- LAN, Pod, and Service CIDRs.
- Upstream DNS servers (default: `1.1.1.1,8.8.8.8`).
- Designating the K3s server, default gateway node, and Harbor service node.

The command validates networking, tests SSH and sudo connectivity, and writes `ansible/inventory.yml` and `ansible/group_vars/all.yml`.

### 3. Configure Service Hostnames and Initial Secrets

Set your desired DNS hostnames (or wildcard/sslip.io domains) and initial passwords:

```bash
sudo jihwija set hostname rancher rancher.10.42.0.31.sslip.io
sudo jihwija set hostname harbor harbor.10.42.0.31.sslip.io
sudo jihwija set hostname portainer portainer.10.42.0.31.sslip.io
sudo jihwija set hostname argo argo.10.42.0.31.sslip.io

sudo jihwija set secret RANCHER_BOOTSTRAP_PASSWORD
sudo jihwija set secret HARBOR_ADMIN_PASSWORD
```

### 4. Install and Provision K3s

Provision the K3s server, agents, Flannel CNI, and NVIDIA GPU discovery:

```bash
sudo jihwija install k3s
```

Once complete, `jihwija` prints the active cluster nodes:
```text
NAME       STATUS   ROLES                  AGE   VERSION
server-01  Ready    control-plane,master   2m    v1.36.1+k3s1
worker-01  Ready    <none>                 90s   v1.36.1+k3s1
```

### 5. Deploy Cluster Services

Deploy Rancher, Harbor, Portainer, Argo Workflows, cert-manager, and the NVIDIA device plugin:

```bash
sudo jihwija deploy
```

`jihwija deploy` renders the manifests via Kustomize, waits for database rollouts (such as Harbor PostgreSQL), rolls out all workloads, taints discovered GPU nodes, and distributes cluster certificates.

To force a rolling restart of existing workloads:
```bash
sudo jihwija deploy --redeploy
```

### 6. Distribute Certificate Trust

If you need to refresh certificates or distribute them to newly ready nodes:

```bash
sudo jihwija trust certs
```

This installs ingress TLS certificates and private CAs into:
1. The Ubuntu system CA store (`/usr/local/share/ca-certificates/k3s`).
2. Chromium enterprise policy (`/etc/chromium/policies/managed`).
3. K3s containerd registry trust on every Ready node.

### 7. Post-Installation Service Access & API Keys

If your local computer cannot reach the cluster network directly, follow [docs/TUNNELING.md](TUNNELING.md) to access the web UIs via SOCKS5 proxy.

1. **Harbor:** Browse to `https://harbor.<your-domain>` and log in as `admin` using `HARBOR_ADMIN_PASSWORD`.
2. **Portainer:** Browse to `https://portainer.<your-domain>` and complete initial admin account setup. Navigate to **Account settings -> Access tokens** to create an API key, then store it:
   ```bash
   sudo jihwija set secret PORTAINER_API_KEY
   ```
3. **Rancher:** Browse to `https://rancher.<your-domain>` and log in as `admin` using `RANCHER_BOOTSTRAP_PASSWORD`. Create a permanent password and generate an API key (**Account -> API & Keys**), then store it:
   ```bash
   sudo jihwija set secret RANCHER_TOKEN
   ```

### 8. Manage Worker Nodes

Add a worker node. Jihwija validates SSH, sudo, Ubuntu version, network addressing, and CPU architecture, updates the inventory, and immediately reconciles K3s:

```bash
sudo jihwija add node worker-04 10.42.0.40
```

Remove an ordinary worker by cordoning, draining Pods, uninstalling its K3s agent, deleting the Kubernetes Node resource, and removing its inventory entry:

```bash
sudo jihwija remove node worker-04
```

The K3s server, gateway, and designated Jihwija service nodes are protected from removal. Add `--delete-emptydir-data` only when temporary Pod data may be safely discarded.

### 9. Multi-Tenant User Management with the CLI

Enable user filesystem storage quotas on the target mount (e.g. `/home`):
```bash
sudo jihwija enable quotas /home
```

Provision a multi-tenant user across Linux, K3s namespace, Argo Workflows, Harbor, Rancher, Portainer, and rootless Docker:
```bash
sudo jihwija add user alice
```

Modify quotas or passwords:
```bash
sudo jihwija set user quota alice --linux-quota 10GB
sudo jihwija set user password alice
```

Remove a user when finished:
```bash
sudo jihwija remove user alice --yes
```

> [!TIP]
> For a complete walkthrough of user lifecycle operations, interactive vs automated flags, selective component provisioning (`--only`), and service architecture, see the dedicated **[User Setup Guide](SETUP_USERS.md)**.

---

## Option B: Manual Native Setup

This is the original native workflow. Maintainers can execute each playbook, script, and manifest directly without installing the CLI overlay.

```
k3s-turing-pi/
├── ansible/                  # Ansible playbooks and inventory
├── argo/                     # Argo Workflow Runner RBAC & examples
├── etc/                      # Environment variables and profile scripts
├── jihwija-services/         # Kustomize service manifests
└── scripts/plumbing-scripts/ # Direct maintenance executables
```

### 1. Configure the Ansible Inventory

1. Copy the example inventory and group variables:
   ```bash
   cp ansible/inventory.example.yml ansible/inventory.yml
   cp ansible/group_vars/all.example.yml ansible/group_vars/all.yml
   ```

2. Edit `ansible/group_vars/all.yml` to specify:
   - `k3s_lan_cidr`: Local subnet (e.g. `10.42.0.0/24`)
   - `k3s_cluster_cidr`: Pod network (e.g. `10.244.0.0/16`)
   - `k3s_service_cidr`: Service network (e.g. `10.43.0.0/16`)
   - `k3s_dns_servers`: Upstream DNS (`["1.1.1.1", "8.8.8.8"]`)

3. Edit `ansible/inventory.yml` to define your nodes and role assignments:
   ```yaml
   all:
     vars:
       ansible_user: operator
       k3s_version: v1.36.1+k3s1
     children:
       servers:
         hosts:
           turing-master:
             ansible_host: 10.42.0.10
             k3s_host: true
             is_default_gateway: true
       workers:
         hosts:
           turing-node-01:
             ansible_host: 10.42.0.11
             is_jihwija_service_node: true  # MUST be AMD64 for Harbor
           turing-node-02:
             ansible_host: 10.42.0.12
             is_desktop_node: false
           turing-orin:
             ansible_host: 10.42.0.20
   ```

   **Key Inventory Host Flags:**
   - `k3s_host: true`: Exactly one node must have this (the K3s server).
   - `is_default_gateway: true`: Exactly one node (if acting as the router/gateway for the cluster LAN).
   - `is_jihwija_service_node: true`: At least one node. The setup playbook assigns the Kubernetes label `jihwija-services=true`. Harbor components require this node to be **AMD64**.
   - `is_desktop_node: true`: Nodes running desktop/GUI environments.

### 2. Configure Default Gateway (Optional / Turing Pi LANs)

If your controller acts as the central router bridging cluster nodes to the Internet:

```bash
cd ansible
ansible-playbook -i inventory.yml setup-default-gateway.yml
cd ..
```

*Verify from a worker node:* `ping google.com` or `curl -I https://ubuntu.com` to confirm Internet routing.

### 3. Distribute Hostnames Across `/etc/hosts`

Populate `/etc/hosts` across all nodes so they can resolve each other by inventory hostname:

```bash
cd ansible
ansible-playbook -i inventory.yml distribute-hostnames.yml
cd ..
```

### 4. Install Common and Desktop Packages

Install standard packages across all nodes:
```bash
cd ansible
ansible-playbook -i inventory.yml setup-common-packages.yml
```

If you have GUI nodes marked with `is_desktop_node: true`:
```bash
ansible-playbook -i inventory.yml setup-desktop-packages.yml
cd ..
```

### 5. Provision K3s

Deploy and reconcile K3s:

```bash
cd ansible
ansible-playbook -i inventory.yml setup-k3s.yml
cd ..
```

This installs K3s server on `k3s_host: true`, installs K3s agents on all other nodes, distributes `/etc/rancher/k3s/k3s.yaml`, and starts systemd services.

Next, bootstrap NVIDIA device discovery and taint GPU nodes so workloads are not scheduled on GPU hardware unless they explicitly request it:
```bash
sudo ./scripts/plumbing-scripts/deploy-services.py --service nvidia --timeout 10m
```

Verify that all nodes are ready:
```bash
k3s kubectl get nodes -o wide
```

### 6. Configure Service Environment and Secrets

1. Create `etc/jihwija.env` (permissions `0600`):
   ```bash
   cp etc/jihwija.env.example etc/jihwija.env
   chmod 600 etc/jihwija.env
   ```

2. Edit `etc/jihwija.env` with your hostnames and passwords:
   ```bash
   export RANCHER_HOSTNAME="rancher.10.42.0.31.sslip.io"
   export HARBOR_HOSTNAME="harbor.10.42.0.31.sslip.io"
   export PORTAINER_HOSTNAME="portainer.10.42.0.31.sslip.io"
   export ARGO_HOSTNAME="argo.10.42.0.31.sslip.io"

   export HARBOR_ADMIN_PASSWORD="YourStrongHarborPassword123!"
   export RANCHER_BOOTSTRAP_PASSWORD="YourStrongRancherPassword123!"
   ```

### 7. Deploy Cluster Services

Deploy cert-manager, Harbor, Rancher, Portainer, and Argo Workflows:

```bash
sudo ./scripts/plumbing-scripts/deploy-services.py
```

Alternatively, to render and apply via standard `kubectl` without the script:
```bash
k3s kubectl kustomize jihwija-services | k3s kubectl apply -f -
```

### 8. Distribute Certificate Trust

After ingress TLS certificates have been generated by cert-manager, distribute trust cluster-wide:

```bash
sudo ./scripts/plumbing-scripts/trust-k3s-certs.py
```

This configures containerd registry trust on every worker node so containerd can pull images from the local Harbor registry without x509 certificate errors.

### 9. Configure Web UI API Tokens

1. **Harbor:** Log in at `https://<HARBOR_HOSTNAME>` as `admin`.
2. **Portainer:** Open `https://<PORTAINER_HOSTNAME>`, set the admin password, navigate to **Account settings -> Access tokens**, create an API key, and add it to `etc/jihwija.env`:
   ```bash
   export PORTAINER_API_KEY="ptr_..."
   ```
3. **Rancher:** Open `https://<RANCHER_HOSTNAME>`, log in with `RANCHER_BOOTSTRAP_PASSWORD`, set a permanent password, generate an API token (**Account -> API & Keys**), and add it to `etc/jihwija.env`:
   ```bash
   export RANCHER_TOKEN="token-..."
   ```

### 10. Worker Node Management (Native Plumbing Scripts)

Maintainers can add and remove worker nodes using direct plumbing scripts:

1. **Add a Worker Node:**
   ```bash
   sudo ./scripts/plumbing-scripts/add-node.py worker-04 10.42.0.40
   ```
   This validates node prerequisites, updates the Ansible inventory, and runs the K3s setup playbook for the new host.

2. **Remove a Worker Node:**
   ```bash
   sudo ./scripts/plumbing-scripts/remove-node.py worker-04
   ```
   This cordons and drains the node, uninstalls the K3s agent, removes the Kubernetes Node object, and prunes the inventory.

### 11. Manual User Provisioning

1. Enable filesystem quotas on the target home partition:
   ```bash
   sudo ./scripts/plumbing-scripts/enable-quotas.py /home
   ```

2. Install system-wide profile scripts for automatic Kubeconfig and Argo variable export:
   ```bash
   sudo install -D -o root -g root -m 644 \
     ./etc/profile.d/jihwija-kubeconfig.sh \
     /etc/profile.d/jihwija-kubeconfig.sh

   sudo install -D -o root -g root -m 644 \
     ./etc/profile.d/jihwija-argo-variables.sh \
     /etc/profile.d/jihwija-argo-variables.sh
   ```

3. Provision a user:
   ```bash
   sudo ./scripts/plumbing-scripts/create-user.py -u bob
   ```
   *Options:*
   - `--no-quota`: Skip quota prompts.
   - `--only harbor,rancher`: Provision only specific services.

4. Update passwords or quotas:
   ```bash
   sudo ./scripts/plumbing-scripts/change-user-password.py -u bob
   sudo ./scripts/plumbing-scripts/change-user-quota.py -u bob --linux-quota 20GB
   ```

5. Remove a user:
   ```bash
   sudo ./scripts/plumbing-scripts/remove-user.py -u bob --yes
   ```

> [!TIP]
> For in-depth instructions on manual plumbing scripts, individual component installers (`install-docker-rootless.py`, `install-portainer-agent.py`, `install-k3s-namespace.py`, etc.), per-user state files, and teardown procedures, see the dedicated **[User Setup Guide](SETUP_USERS.md)**.

---

## Command Reference

See the dedicated **[CLI Command Reference](CLI_REFERENCE.md)** for every CLI
route and its directly executable native equivalent.

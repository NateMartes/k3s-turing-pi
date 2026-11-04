# Managed K3s Turing Pi Cluster

Welcome to an overview of a Turing Pi Cluster with K3s, Rancher, and more!

Currently this setup supports:

- Ansible provisioning of K3s and more.
- K3s deployment on Turing Pi nodes.
- Rancher deployment into K3s.
- Harbor registry deployment into K3s.
- Portainer deployment into K3s.
- User management and automated account creation for:
  - Linux
  - Portainer
  - Rancher

## Directories

- `ansible`: Automated playbooks to install and set up software.
- `etc`: Templates for files distributed to each node's `/etc` directory.
- `scripts`: Programs to set up software for users and system-wide use.
- `sysadmin-services`: Services running on this cluster, deployed via Kubernetes.

## Getting Started

0. Download the repository.

   Using Git:

   ```bash
   git clone https://github.com/NateMartes/k3s-turing-pi.git
   cd k3s-turing-pi
   ```

   Alternatively, download the `master` branch as a tarball and extract it
   directly into a `k3s-turing-pi` directory:

   ```bash
   curl --fail --location \
     https://github.com/NateMartes/k3s-turing-pi/archive/refs/heads/master.tar.gz \
     --output k3s-turing-pi.tar.gz
   mkdir -p k3s-turing-pi
   tar --extract --gzip \
     --file k3s-turing-pi.tar.gz \
     --directory k3s-turing-pi \
     --strip-components=1
   cd k3s-turing-pi
   ```

  **NOTE**: You probably want to keep some of your files around if you ever pull
  an updated version of this repo (like `inventory.yml`)

   ```bash
   tar --extract --gzip \
     --file k3s-turing-pi.tar.gz \
     --directory k3s-turing-pi \
     --exclude='*/ansible' \
     --exclude='*/etc/sysadmin-env' \
     --strip-components=1
   ```

   The `*/` prefix matches the top-level directory included in GitHub's source
   archive. Add, remove, or change the exclusion patterns for the paths you do
   not want to extract. Excluding `etc/sysadmin-env` preserves your configured
   hostnames and credentials when updating from a source archive.

1. Set up your nodes. Follow the appropriate guide for your hardware:

   - [Adding a new node (like a RK1)](docs/ADDING_A_NEW_NODE.md)
   - [Adding a Jetson Orin](docs/ADDING_A_JETSON_ORIN.md)

2. Make sure this account has SSH access to all nodes in your cluster:

   ```bash
   ssh-keygen && ssh-copy-id sysadmin@<my-node>
   ```

   Every node should be able to SSH into every other node.

3. Install Ansible on this node:

   ```bash
   sudo apt update && sudo apt install -y ansible
   ```

4. Ensure your node inventory (`ansible/inventory.yml`) points to every node.
   See the inventory variable table in `ansible/README.md` for the supported
   global and per-host settings.

5. Configure the controller as the LAN's default gateway.
   Depending on your setup, you won't have to do this. You might
   A router acting as your default gateway, which is great too! But if you
   don't and you are just using one central manchine to bridge your nodes to the
   outside world, you'll need IP Forwarding:

   ```bash
   cd ansible && ansible-playbook -i inventory.yml setup-default-gateway.yml
   ```

   Exactly one Ubuntu node must have `is_default_gateway: true`.
    This node must already have upstream Internet
   access. The remaining nodes can use its `ansible_host` address as their IPv4
   default gateway once the playbook finishes.

    At this point, go onto one of your nodes and try to `curl` or `ping` a service
    (like `google.com` or `ibm.com`) to make sure you the nodes can reach the internet.

6. Distribute every inventory node's name to `/etc/hosts` on every node.
   This is optional, but nice to have!

   ```bash
   cd ansible && ansible-playbook -i inventory.yml distribute-hostnames.yml
   ```

   This makes each node reachable by its inventory name (for example,
   `my-very-cool-box`).

7. Install common packages using Ansible:

   ```bash
   cd ansible && ansible-playbook -i inventory.yml setup-common-packages.yml
   ```

8. Install desktop packages on GUI nodes:

   ```bash
   cd ansible && ansible-playbook -i inventory.yml setup-desktop-packages.yml
   ```

   - Chromium is reinstalled with Snap since system-wide certificate trusting only
     works in later versions, which `apt` doesn't provide.

   **NOTE**: Only nodes with `is_desktop_node: true` in
   `ansible/inventory.yml` are changed. Nodes where the variable is false or
   missing are skipped.

9. Set up K3s:

   ```bash
   cd ansible && ansible-playbook -i inventory.yml setup-k3s.yml
   ```

   The default K3s Pod network is `10.244.0.0/16`, deliberately separate from
   the `10.42.0.0/24` host LAN. Review `ansible/group_vars/all.yml` before
   provisioning a cluster on a different LAN.
    If in the future you ever add more nodes, just re-run this command to add them
    to the cluster.

10. Deploy sysadmin services to K3s:

   ```bash
   sudo install -D -o root -g root -m 600 \
     ./etc/sysadmin-env /etc/k3s-turing-pi/sysadmin-env
   sudo ./scripts/apply-sysadmin-services
   ```

   The first command copies the repository's configuration into `/etc` with
   permissions that allow only root to read or change it. The administration
   scripts load their configuration from `/etc/k3s-turing-pi/sysadmin-env`
   automatically.

   When values in `etc/sysadmin-env` change, rerun the `install` command above to
   update `/etc/k3s-turing-pi/sysadmin-env`, then rerun the affected
   administration command.

   At this point, the sysadmin services can run on nodes marked
   `is_sysadmin_service_node: true` in `ansible/inventory.yml`. The K3s setup
   playbook gives those nodes the `sysadmin-services=true` Kubernetes label.

   The Rancher, Harbor, and Portainer domain names come from
   `RANCHER_HOSTNAME`, `HARBOR_HOSTNAME`, and `PORTAINER_HOSTNAME` in
   `/etc/k3s-turing-pi/sysadmin-env`. Harbor's initial `admin` password comes from
   `HARBOR_ADMIN_PASSWORD`; Rancher's initial administrator password comes from
   `RANCHER_BOOTSTRAP_PASSWORD`.

11. Trust the certificates from the sysadmin K3s services, including Harbor's
   private CA, and distribute them to every K3s node:

   ```bash
   sudo ./scripts/trust-k3s-crets
   cd ansible && ansible-playbook -i inventory.yml trust-k3s-certs.yml
   ```

12. Log into Harbor at the configured `HARBOR_HOSTNAME` as `admin`, using
    `HARBOR_ADMIN_PASSWORD`. Change the password after the initial login.

13. Log into Portainer at the configured `PORTAINER_HOSTNAME` and create its
    initial administrator account. Then create an API key and set it as
    `PORTAINER_API_KEY` in `etc/sysadmin-env`, then reinstall the file at
    `/etc/k3s-turing-pi/sysadmin-env` for user-management commands.

14. Log into Rancher at the configured `RANCHER_HOSTNAME` as `admin`, using
    `RANCHER_BOOTSTRAP_PASSWORD`. Rancher uses this only for initial setup and
    prompts for the permanent administrator password on first login.

That's it! Now you have K3s running some neat services!

The pinned Harbor release runs on the AMD64 node marked
`is_sysadmin_service_node: true` in `ansible/inventory.yml`. Harbor can store
ARM64, AMD64, and multi-platform images regardless of the registry node's
architecture.

## Users

### Making Users

1. All of the above must be done.

2. Get a Rancher API token from the current Rancher instance.

   From the UI, log in, and then go to your account and create an API key.
   Set the key as `RANCHER_TOKEN` in `etc/sysadmin-env`, reinstall it at
   `/etc/k3s-turing-pi/sysadmin-env`. The file's `RANCHER_HOSTNAME` selects the
   Rancher instance used by the scripts.

3. Get a Portainer API token from the current Portainer instance.

   From the UI, log in, and then go to your account and create an API key.
   Set the key as `PORTAINER_API_KEY` in `etc/sysadmin-env`, then reinstall it at
   `/etc/k3s-turing-pi/sysadmin-env`. The file also specifies
   `PORTAINER_HOSTNAME` for the Portainer instance used by the scripts.

4. Enable quotas for users:

   ```bash
   sudo ./scripts/enable-quotas /home
   ```

5. Run the create-user script:

   ```bash
   sudo ./scripts/create-user -u <new-user>
   ```

This will make accounts on the services above, automatically.
In the event of failures, you can revert the changes:

```bash
sudo ./scripts/remove-user -u <new-user>
```

### Updating User Passwords

```bash
sudo ./scripts/change-user-password -u <new-user>
```

This will update the passwords in K3s services too!

*Note:* The Portainer account of the user would be reset since Portainer does
not allow a password to be updated.

### Removing Users

```bash
sudo ./scripts/remove-user -u <new-user>
```

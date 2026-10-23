# Managed K3s Turing Pi Cluster

Welcome to an overview of a Turing Pi Cluster with K3s, Rancher, and more!

Currently this setup supports:

- Ansible provisioning of K3s and more.
- K3s deployment on Turing Pi nodes.
- Rancher deployment into K3s.
- Portainer deployment into K3s.
- User management and automated account creation for:
  - Linux
  - Portainer
  - Rancher

## Directories

- `ansible`: Automated playbooks to install and set up software.
- `scripts`: Programs to set up software for users and system-wide use.
- `sysadmin-services`: Services running on this cluster, deployed via Kubernetes.

## Getting Started

0. Pull this down

   ```bash
   git clone https://github.com/NateMartes/k3s-turing-pi.git
   ```

1. Make sure this account has SSH access to all nodes in your cluster:

   ```bash
   ssh-keygen && ssh-copy-id sysadmin@<my-node>
   ```

   Every node should be able to SSH into every other node.

2. Install Ansible on this node:

   ```bash
   sudo apt update && sudo apt install -y ansible
   ```

3. Ensure your node inventory (`ansible/inventory.yml`) points to every node.

4. Install common packages using Ansible:

   ```bash
   cd ansible && ansible-playbook -i inventory.yml setup-common-packages.yml
   ```

5. Install desktop packages to GUI nodes (will be only 1 node):

   ```bash
   cd ansible && ansible-playbook -i inventory.yml -l <my-GUI-node-hostname> setup-desktop-packages.yml
   ```

   - Chromium is reinstalled with Snap since system-wide certificate trusting only
     works in later versions, which `apt` doesn't provide.

6. Set up K3s:

   ```bash
   cd ansible && ansible-playbook -i inventory.yml setup-k3s.yml
   ```

   The default K3s Pod network is `10.244.0.0/16`, deliberately separate from
   the `10.42.0.0/24` host LAN. Review `ansible/group_vars/all.yml` before
   provisioning a cluster on a different LAN.

7. Deploy sysadmin services to K3s:

   ```bash
   source ./sysadmin-env
   sudo -E ./scripts/apply-sysadmin-services
   ```

   At this point, the sysadmin services will be running on the K3s server node,
   which you have defined in `ansible/inventory.yml`.

   The Rancher and Portainer domain names come from `RANCHER_HOSTNAME` and
   `PORTAINER_HOSTNAME` in `sysadmin-env`.

8. Trust the certificates from the sysadmin K3s services if you are using self-signed certificates:

   ```bash
   cd $HOME && sudo -E ./scripts/trust-k3s-certs
   ```

9. Log into Portainer (currently at `portainer.<server-node-ip>.sslip.io`) for the first time.

   - It's probably a good idea to set the password of the default admin, `admin`,
     to this user's password.

10. Log into Rancher (currently at `rancher.<server-node-ip>.sslip.io`) for the first time.

    - Same as above, set `admin` to this user's password.

That's it! Now you have K3s running some neat services!

## Users

### Making Users

1. All of the above must be done.

2. Get a Rancher API token from the current Rancher instance.

   From the UI, log in, and then go to your account and create an API key.
   Set the key as `RANCHER_TOKEN` in `sysadmin-env`. The file also specifies
   `RANCHER_HOSTNAME` for the Rancher instance used by the scripts.

3. Get a Portainer API token from the current Portainer instance.

   From the UI, log in, and then go to your account and create an API key.
   Set the key as `PORTAINER_API_KEY` in `sysadmin-env`. The file also specifies
   `PORTAINER_HOSTNAME` for the Portainer instance used by the scripts. Then run
   `source sysadmin-env` before the user-management commands.

4. Enable quotas for users:

   ```bash
   sudo ./scripts/enable-quotas /home
   ```

5. Run the create-user script:

   ```bash
   sudo -E ./scripts/create-user -u <new-user>
   ```

This will make accounts on the services above, automatically.
In the event of failures, you can revert the changes:

```bash
sudo -E ./scripts/remove-user -u <new-user>
```

### Updating User Passwords

```bash
sudo -E ./scripts/change-user-password -u <new-user>
```

This will update the passwords in K3s services too!

*Note:* The Portainer account of the user would be reset since Portainer does
not allow a password to be updated.

### Removing Users

```bash
sudo -E ./scripts/remove-user -u <new-user>
```

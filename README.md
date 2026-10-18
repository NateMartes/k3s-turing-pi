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

0. Pull this down, and store it in `$HOME`

   **Note**: The commands are taking from the POV of `$HOME`, so if you planning something
   different, please double check commands (not saying you would NOT double check them already...)

   This copies this repo into your `$HOME`, but also **overwrites any match file names**, so
   be careful...
   ```bash
   curl -fsSL https://github.com/NateMartes/k3s-turing-pi/archive/HEAD.tar.gz \
     | tar -xz --strip-components=1 -C "$HOME"
   ```

   you could also...
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
   cd $HOME/ansible && ansible-playbook -i inventory.yml setup-common-packages.yml
   ```

5. Install desktop packages to GUI nodes (will be only 1 node):

   ```bash
   cd $HOME/ansible && ansible-playbook -i inventory.yml -l <my-GUI-node-hostname> setup-desktop-packages.yml
   ```

   - Chromium is reinstalled with Snap since system-wide certificate trusting only
     works in later versions, which `apt` doesn't provide.

6. Set up K3s:

   ```bash
   cd $HOME/ansible && ansible-playbooks -i inventory.yml setup-k3s.yml
   ```

7. Deploy sysadmin services to K3s:

   ```bash
   cd $HOME && sudo kubectl apply -k sysadmin-services
   ```

   At this point, the sysadmin services will be running on the K3s server node,
   which you have defined in `ansible/inventory.yml`.

   If you want to find the specific defined domain names to reach the services,
   check out `sysadmin-services/portainer.yml` and `sysadmin-services/rancher.yml`,
   for instance.

8. Trust the certificates from the sysadmin K3s services if you are using self-signed certificates:

   ```bash
   cd $HOME && sudo ./scripts/trust-k3s-certs
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
   Store this key in `$HOME/scripts/user_common.py` as the `RANCHER_API_KEY`.

3. Get a Portainer API token from the current Portainer instance.

   From the UI, log in, and then go to your account and create an API key.
   Store this key in `$HOME/scripts/user_common.py` as the `PORTAINER_API_KEY`.

4. Enable quotas for users:

   ```bash
   cd $HOME && ./scripts/enable-quotas /home
   ```

5. Run the create-user script:

   ```bash
   cd $HOME && ./scripts/create-user -u <new-user>
   ```

This will make accounts on the services above, automatically.
In the event of failures, you can revert the changes:

```bash
cd $HOME && ./scripts/remove-user -u <new-user>
```

### Updating User Passwords

```bash
cd $HOME && ./scripts/change-user-password -u <new-user>
```

This will update the passwords in K3s services too!

*Note:* The Portainer account of the user would be reset since Portainer does
not allow a password to be updated.

### Removing Users

```bash
cd $HOME && ./scripts/remove-user -u <new-user>
```

# Managed K3s Turing Pi Cluster

Welcome to a overview of a Turing Pi Cluster with K3s, Rancher, and More!
Currently this setup supports:

 - Ansible provisioning of K3s and more.
 - K3s Deployment on Turing Pi Nodes.
 - Rancher Deployment into K3s.
 - Portainer Deployment into K3s.
 - User management and automated account creation for
    - Linux
    - Portainer
    - Rancher

## Directories
`ansible`: Automated Playbooks to install and setup software
`scripts`: Programs to setup software for users and system wide
`sysadmin-services`: Services running on this cluster deployed via Kubernetes


## Getting Started
1. Make sure all nodes in your cluster, THIS account has SSH access to
`ssh-keygen && ssh-copy-id sysadmin@my-node`

Every node should be able to ssh into every other node

2. Install ansible on this node
`sudo apt update && sudo apt install -y ansible`

3. Ensure your node inventory (`ansible/inventory.yml`) points to every node.

4. Install common packages using ansible:
`cd $HOME/ansible && ansible-playbook -i inventory.yml setup-common-packages.yml`

5. Install desktop packages to GUI nodes (will be only 1 node):
`cd $HOME/ansible && ansible-playbook -i inventory.yml -l <my-GUI-node-hostname> setup-desktop-packages.yml`

 - Chromium is reinstalled with snap since system wide certificate trusting only works in later versions, which
   which `apt` doesn't provide

6. Setup K3s
`cd $HOME/ansible && ansible-playbooks -i inventory.yml setup-k3s.yml`

7. Deploy sysadmin services to K3s
`cd $HOME && sudo kubectl apply -k sysadmin-services`

At this point, the sysadmin services will be running on the K3s server node,
which you have defined from the `ansible/inventory.yml`.

If you want to find the specific defined domain names to reach the services,
check out `sysadmin-services/portainer.yml` and `sysadmin-services/rancher.yml`
for instance.

8. Trust the certificates from the sysadmin K3s services if you are using self-singed certs
`cd $HOME && sudo ./scripts/trust-k3s-certs`

9. Log into portainer (currently at portainer.<server-node-ip>.sslip.io) for the first time
    - Its probably a good idea to set the password of the the default admin, `admin` to
      This user's password.

10. Log into rancher (currently at rancher.<server-node-ip>.sslip.io) for the first time
    - Same with above, set `admin` to this user's password

Thats it! now you have a K3s running some neat services!


## Users

### Making Users
1. All of the above must be done

2. Get a Rancher API Token from the current Rancher instance
From the UI, login, and then go to your account and create an API key.
Store this key in `$HOME/scripts/user_common.py` as the `RANCHER_API_KEY`

3. Get a Portainer API Token from the current Portainer instance
From the UI, login, and then go to your account and create an API key.
Store this key in `$HOME/scripts/user_common.py` as the `PORTAINER_API_KEY`

4. Enable Quotas for Users
`cd $HOME && ./scripts/enable-quotas /home`

5. Run the create user script
`cd $HOME && ./scripts/create-user -u <new-user>`

This will make accounts on the services above, automatically.
In the event of failures, you can revert the changes
`cd $HOME && ./scripts/remove-user -u <new-user>`

### Updating User Passwords
`cd $HOME && ./scripts/change-user-password -u <new-user>`

This will update the passwords in K3s services too!
*Note*: the Portainer account of the user would be reset since Portainer does
not allow a password to be updated

### Removing Users
`cd $HOME && ./scripts/remove-user -u <new-user>`



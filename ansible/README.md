Before running anything, make sure every node:

1. Has the `sysadmin` user and it has sudo access
2. Has access to the internet
3. Can be SSH'd into via THIS node (ssh-keygen && ssh-copy-id <node-ip>)

## Playbooks

To run them use:
```bash
ansible-playbook <playbook> -i inventory.yml
```
inventory.yml: The nodes within the cluster, also specifying a K3s server node
setup-k3s.yml: Sets up K3s with 1 server node and the rest agent nodes
remove-k3s.yml: Removes K3s from all nodes
setup-common-packages.yml: Sets up all nodes to have common packages throughout
setup-desktop-packages.yml: Installs specific packages for nodes with GUIs

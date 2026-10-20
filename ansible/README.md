# Ansible Playbooks

Before running anything, make sure every node:

1. Has the `sysadmin` user, and it has sudo access.
2. Has access to the internet.
3. Can be accessed by SSH via this node (`ssh-keygen && ssh-copy-id <node-ip>`).

# Playbooks

To run them, use:

```bash
ansible-playbook <playbook> -i inventory.yml
```

- `inventory.yml`: The nodes within the cluster, also specifying a K3s server node.
- `setup-k3s.yml`: Sets up K3s with 1 server node and the rest as agent nodes.
- `remove-k3s.yml`: Removes K3s from all nodes.
- `setup-common-packages.yml`: Sets up all nodes to have common packages throughout.
- `setup-desktop-packages.yml`: Installs specific packages for nodes with GUIs.

## K3s networking

Cluster network defaults are stored in `group_vars/all.yml`:

- Host LAN: `10.42.0.0/24`
- Pod network: `10.244.0.0/16`
- Service network: `10.43.0.0/16`
- Flannel interface: `end1`

The setup playbook stops before changing K3s if these networks overlap or a
node's `ansible_host` address is outside the configured LAN. The Pod network
supports additional nodes without assigning Pod addresses from the physical
LAN. Changing the Pod or Service CIDR of an existing cluster requires removing
and reinstalling K3s; restarting an existing cluster is not a migration.

`remove-k3s.yml` is destructive. It removes K3s state, local K3s storage, CNI
configuration, and residual Flannel/CNI interfaces from every inventory node.

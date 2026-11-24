# Ansible Playbooks

Before running the playbooks, make sure every node:

1. Has the SSH operator selected in the inventory, with sudo access.
2. Can be accessed by SSH via this node (`ssh-keygen && ssh-copy-id <node-ip>`).

The node marked `is_default_gateway: true` must also have upstream Internet
access. Run `setup-default-gateway.yml` first; the remaining nodes can use that
gateway for Internet access during subsequent playbooks.

# Playbooks

To run them, use:

```bash
ansible-playbook <playbook> -i inventory.yml
```

- `inventory.yml`: The generated live cluster inventory; use
  `inventory.example.yml` as a format reference. Set `k3s_host: true` on exactly one K3s
  server, `is_default_gateway: true` on exactly one Ubuntu gateway, and
  `is_jihwija_service_node: true` on each node that should run Jihwija
  workloads.
- `distribute-hostnames.yml`: Adds every inventory node to the managed cluster
  block in `/etc/hosts` on every node, using its inventory name.
- `setup-default-gateway.yml`: Configures the one Ubuntu node marked
  `is_default_gateway: true` to route and NAT IPv4 traffic for the LAN.
- `setup-dhcp.yml`: Removes static IPv4 addresses, gateways, and routes from
  each node's LAN interface and enables Netplan DHCPv4. It stages and validates
  changes by default so an address change does not unexpectedly terminate SSH.
- `setup-k3s.yml`: Sets up K3s with 1 server node and the rest as agent nodes.
- `restart-k3s.yml`: Restarts the K3s server and agents one node at a time.
- `remove-k3s.yml`: Removes K3s from all nodes.
- `setup-common-packages.yml`: Sets up all nodes to have common packages throughout.
- `setup-desktop-packages.yml`: Installs specific packages for nodes with GUIs.

## Inventory variables

Variables under `all.vars` apply to every inventory node. Variables beneath a
host apply only to that node and override an inherited value with the same
name.

| Variable | Scope | Requirement/default | Description |
| --- | --- | --- | --- |
| `ansible_user` | All nodes | Optional; Jihwija prompts for it and otherwise uses the invoking operator. | SSH account Ansible uses to connect to each node. The account must have sudo access. |
| `k3s_version` | All nodes | Required by `setup-k3s.yml`. | Exact K3s release installed on every server and agent, such as `v1.36.1+k3s1`. |
| `ansible_host` | Per host | Required for every node. | IP address or resolvable hostname Ansible uses for SSH. It is also written to the managed `/etc/hosts` block by `distribute-hostnames.yml`. |
| `k3s_host` | Per host | Exactly one node must be `true`; missing values default to `false`. | Selects the K3s server. Every other inventory node becomes a K3s agent. |
| `is_default_gateway` | Per host | Exactly one node must be `true`; missing values default to `false`. | Selects the Ubuntu node configured by `setup-default-gateway.yml` to route and NAT LAN IPv4 traffic. |
| `is_jihwija_service_node` | Per host | At least one node must be `true`; missing values default to `false`. | Adds the Kubernetes label `jihwija-services=true`, allowing selected Jihwija workloads to run on the node. Harbor additionally requires that a selected node be AMD64. |
| `is_desktop_node` | Per host | Optional; defaults to `false`. | Allows `setup-desktop-packages.yml` to modify the node. Nodes without this flag are skipped. |
| `k3s_flannel_iface` | All nodes or per host | Optional; defaults to an empty string in `group_vars/all.yml`. | Pins Flannel to a stable network interface. Leave empty to let Flannel select the interface that routes the node IP. |
| `k3s_snapshotter` | All nodes or per host | Optional; an empty or missing value keeps the K3s default. | Overrides the containerd snapshotter. The Docker test environment uses `native` because OverlayFS cannot be nested on every host. |
| `netplan_dhcp_apply` | All nodes | Optional; defaults to `false`. | Applies the validated Netplan DHCP configuration immediately. Leave false to stage it safely. |
| `netplan_dhcp_interface` | Per host | Optional; discovered from `ansible_host` by default. | Overrides the Linux LAN interface configured by `setup-dhcp.yml`. |
| `netplan_dhcp_definition` | Per host | Optional; defaults to the selected interface name. | Overrides the Netplan Ethernet definition ID when it differs from the Linux interface name. |
| `default_gateway_lan_cidr` | All nodes or gateway host | Optional; defaults to `k3s_lan_cidr`. | IPv4 LAN routed and masqueraded by the default gateway. |
| `default_gateway_lan_interface` | Gateway host | Optional; automatically selects the interface carrying `ansible_host`. | Overrides the gateway's switch/LAN interface. |
| `default_gateway_wan_interface` | Gateway host | Optional; automatically selects Ubuntu's current default-route interface. | Overrides the gateway's upstream/Internet interface. |

The names used as host keys, such as `vision`, are the nodes' Ansible inventory
names. `distribute-hostnames.yml` installs those names into `/etc/hosts` on
every node.

## DHCP client configuration

Run the DHCP playbook after the DHCP server reservations have been saved. The
playbook discovers the interface carrying each node's current `ansible_host`,
removes static addresses, gateways, and routes from that Netplan definition,
enables DHCPv4, and runs `netplan generate`. It also stores a one-time backup at
`/var/backups/netplan-before-ansible-dhcp.tar.gz` on each node.

The safe default writes and validates the persistent configuration without
changing the live network immediately. The staged configuration will still
take effect on the next reboot:

```bash
ansible-playbook -i inventory.yml setup-dhcp.yml
```

Review the output and the DHCP reservations, then apply a single node with:

```bash
ansible-playbook -i inventory.yml setup-dhcp.yml \
  --limit 1wol-hakgwang \
  -e netplan_dhcp_apply=true
```

Applying Netplan can terminate the current SSH connection if DHCP assigns a
different address. Update `ansible_host`, verify the node, and repeat with the
next node. If discovery is ambiguous, set `netplan_dhcp_interface` for that
host. Also set
`netplan_dhcp_definition` when its Netplan definition ID differs from the Linux
interface name, such as a definition selected with `match.macaddress`.

This playbook makes the DHCP server authoritative for addressing, but it does
not suppress normal DHCP renewal requests for a client's current lease.

## Default gateway

`setup-default-gateway.yml` enables IPv4 forwarding and installs persistent,
managed `iptables` forwarding and masquerade rules. The selected node must run
Ubuntu and must already have its stable `ansible_host` address assigned. That
address is the gateway address that should be assigned to LAN clients by DHCP
or configured on those clients manually.

By default, the playbook finds the LAN interface that owns `ansible_host` and
uses the interface for Ubuntu's existing default route as the WAN interface.
Set the interface override variables in `inventory.yml` if that routing state
does not identify the desired interfaces. The playbook supports a one-interface
gateway as well as a conventional two-interface gateway.

## K3s networking

Cluster network defaults are generated in `group_vars/all.yml`; the shipped
defaults are documented in `group_vars/all.example.yml`:

- Host LAN: `10.42.0.0/24`
- Pod network: `10.244.0.0/16`
- Service network: `10.43.0.0/16`
- Upstream DNS: `1.1.1.1`, through a K3s-managed resolver file
- Flannel interface: automatically selected from the node route

The setup playbook stops before changing K3s if these networks overlap or a
node's `ansible_host` address is outside the configured LAN. The Pod network
supports additional nodes without assigning Pod addresses from the physical
LAN. Changing the Pod or Service CIDR of an existing cluster requires removing
and reinstalling K3s; restarting an existing cluster is not a migration.

The playbook writes `k3s_dns_servers` to `k3s_resolv_conf` on every server and
agent and configures K3s to use that file. This prevents CoreDNS and ordinary
Pods from inheriting an unusable resolver advertised by a node interface or
DHCP lease. Change `k3s_dns_servers` in `group_vars/all.yml` if the cluster
should use a different upstream resolver.

`k3s_flannel_iface` is empty by default so a reboot or a new node with a
different interface name does not prevent K3s from starting. Set it per host in
`inventory.yml` only when the interface name is known to be stable.

`remove-k3s.yml` is destructive. It removes K3s state, local K3s storage, CNI
configuration, and residual Flannel/CNI interfaces from every inventory node.

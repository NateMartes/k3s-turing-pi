# Docker test cluster

This fixture creates three Ubuntu 24.04 systemd containers with fixed addresses
on an isolated Docker bridge. The normal Ansible playbooks install one K3s
server and two K3s agents, after which the repository's service deployment
script can install Rancher, Harbor, Portainer, Argo Workflows, cert-manager,
and the NVIDIA discovery stack.

## Requirements and safety

- Linux with Docker Engine and Docker Compose v2. Docker Desktop does not
  normally expose bridge-network addresses directly to its host.
- An AMD64 host for the complete service bundle because Harbor is pinned to
  AMD64 nodes.
- At least 12 GB of free memory and 40 GB of free disk are recommended for the
  complete bundle.

The nodes are privileged containers because nested K3s and systemd need cgroup,
network, and kernel-module access. Use this fixture only on a development
machine, and do not run untrusted workloads in it. The `ansible` password and
service credentials are intentionally public test values.

Git and the other node prerequisites are installed in the test image. If you
install additional Ubuntu packages interactively, refresh the package index in
that ephemeral container first with `apt-get update`.

## Start and provision the nodes

Run these commands from this directory:

```bash
docker compose up --detach --build --wait
docker compose exec operator \
  ansible all --inventory inventory.yml --module-name ping
docker compose exec operator \
  ansible-playbook --inventory inventory.yml ../../ansible/distribute-hostnames.yml
docker compose exec operator \
  ansible-playbook --inventory inventory.yml ../../ansible/setup-common-packages.yml
docker compose exec operator \
  ansible-playbook --inventory inventory.yml ../../ansible/setup-k3s.yml
```

Do not run `setup-dhcp.yml` or `setup-default-gateway.yml` in this fixture.
Docker owns the test nodes' addresses, default routes, and external NAT. The
gateway marker remains in the inventory so it has the same shape as a live
cluster inventory. The inventory also selects containerd's `native`
snapshotter because Docker's OverlayFS cannot reliably host a nested OverlayFS
mount. This is slower than the production default but suitable for tests.

Verify the cluster from the controller:

```bash
docker compose exec controller k3s kubectl get nodes -o wide
```

## Deploy the service bundle

The repository is mounted read-only at `/workspace` in each node. Run the
deployment from the K3s server so the script can use its local kubeconfig and
the test nodes' internal SSH key:

```bash
docker compose exec controller env \
  JIHWIJA_ENV_FILE=/workspace/tests/test-env/jihwija.env \
  /workspace/scripts/plumbing-scripts/deploy-services.py --timeout 45m
```

Inspect the resulting workloads with:

```bash
docker compose exec controller k3s kubectl get pods --all-namespaces
docker compose exec controller k3s kubectl get helmcharts --namespace kube-system
```

On a Linux host, the service names in `jihwija.env` resolve through `sslip.io`
to the controller's bridge address. For example, Rancher is available at
`https://rancher.172.31.42.10.sslip.io`. The Compose file also publishes HTTP,
HTTPS, and the Kubernetes API on localhost ports `18080`, `18443`, and `16443`
for command-line diagnostics.

## Stop or reset

`docker compose stop` preserves the node containers. To remove the complete
ephemeral cluster, including its internally generated SSH key, run:

```bash
docker compose down --volumes --remove-orphans
```

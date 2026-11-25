#!/usr/bin/env bash

# Build a disposable three-node Jihwija cluster, deploy the complete service
# bundle, and leave it running as a local playground.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly INVENTORY=/workspace/tests/test-env/inventory.yml
readonly CONTROLLER_IP=172.31.42.10
readonly SERVICE_TIMEOUT="${JIHWIJA_SERVICE_TIMEOUT:-45m}"

readonly RANCHER_HOSTNAME="rancher.${CONTROLLER_IP}.sslip.io"
readonly HARBOR_HOSTNAME="harbor.${CONTROLLER_IP}.sslip.io"
readonly PORTAINER_HOSTNAME="portainer.${CONTROLLER_IP}.sslip.io"
readonly ARGO_HOSTNAME="argo.${CONTROLLER_IP}.sslip.io"
readonly GRAFANA_HOSTNAME="grafana.${CONTROLLER_IP}.sslip.io"
readonly RANCHER_BOOTSTRAP_PASSWORD="${JIHWIJA_RANCHER_BOOTSTRAP_PASSWORD:-jihwija-playground-rancher}"
readonly HARBOR_ADMIN_PASSWORD="${JIHWIJA_HARBOR_ADMIN_PASSWORD:-jihwija-playground-harbor}"
readonly GRAFANA_ADMIN_PASSWORD="${JIHWIJA_GRAFANA_ADMIN_PASSWORD:-jihwija-playground-grafana}"

ROOT_COMMAND=()
DOCKER_COMMAND=()
COMPOSE_STARTED=0

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

select_root_command() {
    if (( EUID == 0 )); then
        ROOT_COMMAND=()
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        ROOT_COMMAND=(sudo)
    else
        die "Docker installation requires root or passwordless sudo."
    fi
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
        select_root_command
        [[ -r /etc/os-release ]] || die "Install Docker Engine and Docker Compose v2, then rerun this script."
        # shellcheck disable=SC1091
        . /etc/os-release
        [[ "${ID:-}" == ubuntu || "${ID:-}" == debian ]] || \
            die "Automatic Docker installation currently supports Ubuntu and Debian only."

        log "Installing Docker Engine and Docker Compose v2"
        "${ROOT_COMMAND[@]}" apt-get update
        packages=()
        command -v docker >/dev/null 2>&1 || packages+=(docker.io)
        if ! docker compose version >/dev/null 2>&1; then
            if apt-cache show docker-compose-v2 >/dev/null 2>&1; then
                packages+=(docker-compose-v2)
            elif apt-cache show docker-compose-plugin >/dev/null 2>&1; then
                packages+=(docker-compose-plugin)
            else
                die "The configured package repositories do not provide Docker Compose v2."
            fi
        fi
        ((${#packages[@]} > 0)) && \
            "${ROOT_COMMAND[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
    fi

    if docker info >/dev/null 2>&1; then
        DOCKER_COMMAND=(docker)
    else
        select_root_command
        if command -v systemctl >/dev/null 2>&1; then
            "${ROOT_COMMAND[@]}" systemctl start docker
        fi
        if "${ROOT_COMMAND[@]}" docker info >/dev/null 2>&1; then
            DOCKER_COMMAND=("${ROOT_COMMAND[@]}" docker)
        else
            die "Docker is installed, but its daemon is unavailable."
        fi
    fi
    "${DOCKER_COMMAND[@]}" compose version
}

compose() {
    "${DOCKER_COMMAND[@]}" compose --project-directory "$SCRIPT_DIR" \
        --file "$SCRIPT_DIR/docker-compose.yml" "$@"
}

controller() {
    compose exec --no-TTY controller "$@"
}

show_diagnostics() {
    (( COMPOSE_STARTED == 1 )) || return 0
    set +e
    log "Container and Kubernetes diagnostics"
    compose ps
    controller k3s kubectl get nodes -o wide
    controller k3s kubectl get helmcharts -n kube-system
    controller k3s kubectl get pods --all-namespaces -o wide
    controller k3s kubectl get events --all-namespaces --sort-by=.lastTimestamp | tail -n 100
    set -e
}

failure() {
    status=$?
    trap - ERR
    printf 'ERROR: playground setup failed near line %s (exit %s).\n' "$1" "$status" >&2
    show_diagnostics
    printf '\nThe containers were left running for inspection.\n' >&2
    exit "$status"
}

trap 'failure "$LINENO"' ERR

warn_for_small_host() {
    available_memory_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    available_disk_kib=$(df -Pk "$SCRIPT_DIR" | awk 'NR == 2 {print $4}')
    if (( available_memory_kib < 12 * 1024 * 1024 )); then
        printf 'WARNING: less than 12 GiB of memory is available; service pods may be evicted.\n' >&2
    fi
    if (( available_disk_kib < 40 * 1024 * 1024 )); then
        printf 'WARNING: less than 40 GiB of disk is available; image pulls may exhaust the host.\n' >&2
    fi
}

configure_services() {
    log "Configuring local service hostnames and initial passwords"
    controller jihwija set hostname rancher "$RANCHER_HOSTNAME" --no-redeploy
    controller jihwija set hostname harbor "$HARBOR_HOSTNAME" --no-redeploy
    controller jihwija set hostname portainer "$PORTAINER_HOSTNAME" --no-redeploy
    controller jihwija set hostname argo "$ARGO_HOSTNAME" --no-redeploy
    controller jihwija set hostname grafana "$GRAFANA_HOSTNAME" --no-redeploy

    printf '%s' "$RANCHER_BOOTSTRAP_PASSWORD" | \
        compose exec --no-TTY controller \
            jihwija set secret RANCHER_BOOTSTRAP_PASSWORD --stdin
    printf '%s' "$HARBOR_ADMIN_PASSWORD" | \
        compose exec --no-TTY controller \
            jihwija set secret HARBOR_ADMIN_PASSWORD --stdin
    printf '%s' "$GRAFANA_ADMIN_PASSWORD" | \
        compose exec --no-TTY controller \
            jihwija set secret GRAFANA_ADMIN_PASSWORD --stdin
}

print_playground_details() {
    cat <<EOF

The Jihwija playground is running.

  Rancher:   https://${RANCHER_HOSTNAME}
             username: admin
             password: ${RANCHER_BOOTSTRAP_PASSWORD}
  Harbor:    https://${HARBOR_HOSTNAME}
             username: admin
             password: ${HARBOR_ADMIN_PASSWORD}
  Portainer: https://${PORTAINER_HOSTNAME}
             create the initial administrator in the browser
  Argo:      https://${ARGO_HOSTNAME}
  Grafana:   https://${GRAFANA_HOSTNAME}
             username: admin
             password: ${GRAFANA_ADMIN_PASSWORD}

Rancher and Portainer API keys are intentionally not configured. Create them
through their web interfaces if you want to exercise user-management commands.

Inspect the cluster:
  cd ${SCRIPT_DIR}
  docker compose exec controller k3s kubectl get pods --all-namespaces

Remove the playground and its volumes:
  cd ${SCRIPT_DIR}
  docker compose down --volumes --remove-orphans
EOF
}

main() {
    [[ "$(uname -m)" == x86_64 ]] || die "The complete Harbor deployment requires an AMD64/x86_64 host."
    ensure_docker
    warn_for_small_host

    log "Building and starting the disposable nodes"
    compose config --quiet
    COMPOSE_STARTED=1
    compose up --detach --build --wait

    log "Verifying SSH access to every node"
    controller sh -ec '
        for address in 172.31.42.10 172.31.42.11 172.31.42.12; do
            ssh -o BatchMode=yes -o StrictHostKeyChecking=no \
                -o UserKnownHostsFile=/root/.ssh/known_hosts \
                "ansible@$address" true
        done
    '
    compose exec --no-TTY operator \
        ansible all --inventory inventory.yml --module-name ping

    log "Installing the current Jihwija checkout in the controller"
    controller env DEBIAN_FRONTEND=noninteractive /workspace/install.sh

    log "Initializing Jihwija without interactive prompts"
    controller jihwija init "$INVENTORY" \
        --ansible-user ansible \
        --k3s-version v1.36.1+k3s1 \
        --lan-cidr 172.31.42.0/24 \
        --pod-cidr 10.244.0.0/16 \
        --service-cidr 10.43.0.0/16 \
        --dns-server 1.1.1.1 \
        --dns-server 8.8.8.8 \
        --resolv-conf /etc/rancher/k3s/resolv.conf \
        --flannel-interface eth0 \
        --snapshotter native \
        --no-dhcp-apply \
        --dhcp-interface "" \
        --dhcp-definition "" \
        --k3s-server test-controller \
        --service-node test-controller \
        --no-desktop-nodes \
        --gateway-node test-controller \
        --gateway-lan-interface eth0 \
        --gateway-wan-interface eth0 \
        --node-flannel test-controller= \
        --node-flannel test-worker-1= \
        --node-flannel test-worker-2= \
        --node-dhcp-interface test-controller= \
        --node-dhcp-interface test-worker-1= \
        --node-dhcp-interface test-worker-2= \
        --node-dhcp-definition test-controller= \
        --node-dhcp-definition test-worker-1= \
        --node-dhcp-definition test-worker-2=

    configure_services

    log "Installing K3s on the three nodes"
    controller jihwija install k3s
    controller k3s kubectl wait --for=condition=Ready nodes --all --timeout=10m

    log "Deploying the complete Jihwija service bundle"
    controller jihwija deploy --timeout "$SERVICE_TIMEOUT"

    log "All services are ready; leaving the playground running"
    print_playground_details
}

main "$@"

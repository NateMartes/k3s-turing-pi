#!/usr/bin/env bash

# Exercise Jihwija against three disposable Ubuntu/systemd containers. Services
# are installed and removed one at a time to keep the peak resource requirement
# suitable for CI runners.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly INVENTORY=/workspace/tests/test-env/inventory.yml
readonly TEST_ENV=/workspace/tests/test-env/jihwija.env
readonly CONTROLLER_IP=172.31.42.10
readonly SERVICE_TIMEOUT="${JIHWIJA_TEST_SERVICE_TIMEOUT:-45m}"
readonly KEEP_TEST_ENV="${JIHWIJA_TEST_KEEP_ENV:-0}"

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
    controller k3s kubectl get namespaces
    controller k3s kubectl get helmcharts -n kube-system
    controller k3s kubectl get pods --all-namespaces -o wide
    controller k3s kubectl get events --all-namespaces --sort-by=.lastTimestamp | tail -n 100
    set -e
}

cleanup() {
    status=$?
    trap - EXIT
    if (( COMPOSE_STARTED == 1 )); then
        if [[ "$KEEP_TEST_ENV" == 1 ]]; then
            log "Leaving the test cluster running because JIHWIJA_TEST_KEEP_ENV=1"
        else
            log "Removing the test cluster"
            if ! compose down --volumes --remove-orphans; then
                printf 'ERROR: failed to remove the Compose test cluster.\n' >&2
                if (( status == 0 )); then
                    status=1
                fi
            fi
        fi
    fi
    exit "$status"
}

failure() {
    status=$?
    printf 'ERROR: integration test failed near line %s (exit %s).\n' "$1" "$status" >&2
    show_diagnostics
    exit "$status"
}

trap cleanup EXIT
trap 'failure "$LINENO"' ERR

warn_for_small_host() {
    available_memory_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    available_disk_kib=$(df -Pk "$SCRIPT_DIR" | awk 'NR == 2 {print $4}')
    if (( available_memory_kib < 8 * 1024 * 1024 )); then
        printf 'WARNING: less than 8 GiB of memory is available; service tests may be evicted.\n' >&2
    fi
    if (( available_disk_kib < 30 * 1024 * 1024 )); then
        printf 'WARNING: less than 30 GiB of disk is available; image pulls may exhaust the runner.\n' >&2
    fi
}

wait_for_no_bad_pods() {
    namespace=$1
    controller sh -ec '
        namespace=$1
        bad=$(k3s kubectl get pods -n "$namespace" --no-headers 2>/dev/null |
            awk '\''$3 == "Failed" || $3 == "CrashLoopBackOff" || $3 == "ImagePullBackOff" {print}'\'')
        if [ -n "$bad" ]; then
            printf "%s\n" "$bad" >&2
            exit 1
        fi
    ' sh "$namespace"
}

curl_service() {
    name=$1
    hostname=$2
    path=$3
    pattern=$4
    log "Checking $name at https://$hostname$path"
    body=$(controller curl --fail --silent --show-error --insecure --location \
        --resolve "$hostname:443:$CONTROLLER_IP" \
        --retry 20 --retry-all-errors --retry-delay 5 --max-time 20 \
        "https://$hostname$path")
    grep -Eqi "$pattern" <<<"$body" || {
        printf 'Unexpected %s response: %s\n' "$name" "$body" >&2
        return 1
    }
}

deploy_service() {
    service=$1
    log "Deploying $service"
    controller env JIHWIJA_ENV_FILE="$TEST_ENV" \
        jihwija deploy --service "$service" --timeout "$SERVICE_TIMEOUT"
}

wait_for_namespace_deletion() {
    namespace=$1
    attempts=${2:-30}
    controller sh -ec '
        namespace=$1
        attempts=$2
        attempt=0
        while [ "$attempt" -lt "$attempts" ]; do
            if ! k3s kubectl get namespace "$namespace" >/dev/null 2>&1; then
                exit 0
            fi
            attempt=$((attempt + 1))
            sleep 2
        done
        exit 1
    ' sh "$namespace" "$attempts"
}

delete_test_namespace() {
    namespace=$1
    controller k3s kubectl delete namespace "$namespace" \
        --ignore-not-found=true --wait=false
    if wait_for_namespace_deletion "$namespace"; then
        return
    fi

    printf 'WARNING: clearing resource finalizers in stuck test namespace %s.\n' \
        "$namespace" >&2
    controller sh -ec '
        namespace=$1
        for resource in $(k3s kubectl api-resources --request-timeout=5s \
            --verbs=list --namespaced -o name); do
            names=$(k3s kubectl get "$resource" -n "$namespace" \
                --request-timeout=5s --ignore-not-found \
                -o jsonpath='\''{range .items[?(@.metadata.finalizers)]}{.metadata.name}{"\n"}{end}'\'' \
                2>/dev/null || true)
            for name in $names; do
                k3s kubectl patch "$resource" "$name" -n "$namespace" \
                    --type=merge --patch '\''{"metadata":{"finalizers":[]}}'\'' \
                    >/dev/null 2>&1 || true
            done
        done
    ' sh "$namespace"
    if wait_for_namespace_deletion "$namespace" 15; then
        return
    fi

    printf 'WARNING: forcing finalization of disposable namespace %s.\n' \
        "$namespace" >&2
    controller sh -ec '
        namespace=$1
        k3s kubectl get namespace "$namespace" --request-timeout=5s -o json |
            python3 -c '\''import json, sys; data=json.load(sys.stdin); data["spec"]["finalizers"]=[]; json.dump(data, sys.stdout)'\'' |
            k3s kubectl replace --raw "/api/v1/namespaces/$namespace/finalize" -f - >/dev/null
    ' sh "$namespace"
    wait_for_namespace_deletion "$namespace" 15
}

teardown_service() {
    service=$1
    case "$service" in
        cert-manager) chart=cert-manager; namespace=cert-manager ;;
        nvidia) chart=nvidia-device-plugin; namespace=nvidia-device-plugin ;;
        rancher) chart=rancher; namespace=cattle-system ;;
        harbor) chart=harbor; namespace=jihwija-system ;;
        portainer) chart=portainer; namespace=jihwija-system ;;
        argo) chart=argo-workflows; namespace=jihwija-system ;;
        *) die "Unknown service teardown: $service" ;;
    esac

    log "Tearing down $service"
    controller k3s kubectl delete helmchart "$chart" -n kube-system \
        --ignore-not-found=true --wait=false

    # Rancher has a post-delete Helm hook that expects its API to remain
    # reachable during uninstall. In a disposable one-service test that hook
    # can fail and leave the HelmChart finalizer retrying forever. Give the
    # controller a short grace period, then finalize only this already-removed
    # test release so the next service can run.
    if ! controller sh -ec '
        chart=$1
        attempt=0
        while [ "$attempt" -lt 30 ]; do
            if ! k3s kubectl get helmchart "$chart" -n kube-system >/dev/null 2>&1; then
                exit 0
            fi
            attempt=$((attempt + 1))
            sleep 2
        done
        exit 1
    ' sh "$chart"; then
        printf 'WARNING: forcing finalization of stuck test HelmChart %s.\n' "$chart" >&2
        controller k3s kubectl patch helmchart "$chart" -n kube-system \
            --type=merge --patch '{"metadata":{"finalizers":[]}}' || true
        controller k3s kubectl delete helmchart "$chart" -n kube-system \
            --ignore-not-found=true --wait=false
    fi
    delete_test_namespace "$namespace"
    controller k3s kubectl delete jobs -n kube-system \
        "helm-install-$chart" "helm-delete-$chart" --ignore-not-found=true
    # Sequential CI runs do not need images from services already tested.
    controller k3s crictl rmi --prune || true
}

verify_nvidia() {
    controller k3s kubectl get daemonsets,deployments -n nvidia-device-plugin
    wait_for_no_bad_pods nvidia-device-plugin
}

verify_cert_manager() {
    controller k3s kubectl wait --for=condition=Available deployment --all \
        -n cert-manager --timeout="$SERVICE_TIMEOUT"
    wait_for_no_bad_pods cert-manager
}

main() {
    [[ "$(uname -m)" == x86_64 ]] || die "The complete Harbor test requires an AMD64/x86_64 host."
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

    log "Installing K3s on the three nodes"
    controller env JIHWIJA_ENV_FILE="$TEST_ENV" jihwija install k3s
    controller k3s kubectl wait --for=condition=Ready nodes --all --timeout=10m

    # K3s installation bootstraps GPU discovery, so validate and remove it
    # before starting the one-service-at-a-time sequence.
    verify_nvidia
    teardown_service nvidia

    # Rancher and Argo require cert-manager. Validate it once and retain it
    # while dependent services are tested, then remove it last.
    deploy_service cert-manager
    verify_cert_manager

    deploy_service rancher
    curl_service Rancher rancher.172.31.42.10.sslip.io /ping '^pong$'
    teardown_service rancher

    deploy_service harbor
    curl_service Harbor harbor.172.31.42.10.sslip.io /api/v2.0/health \
        '"status"[[:space:]]*:[[:space:]]*"healthy"'
    teardown_service harbor

    deploy_service portainer
    curl_service Portainer portainer.172.31.42.10.sslip.io /api/status '"Version"'
    teardown_service portainer

    deploy_service argo
    curl_service "Argo Workflows" argo.172.31.42.10.sslip.io / '<html|<!doctype'
    teardown_service argo

    teardown_service cert-manager
    log "All container-based Jihwija integration tests passed"

    compose down

}

main "$@"

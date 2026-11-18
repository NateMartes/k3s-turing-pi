# Managed by k3s-turing-pi for the Argo Workflows CLI.
# Use the cluster's Argo Server unless the user selected another endpoint.
if [ -z "${ARGO_SERVER:-}" ]; then
    export ARGO_SERVER="argo.10.42.0.31.sslip.io:443"
fi

# Argo Server client authentication expects the Kubernetes token with a
# "Bearer " prefix. Read it from the user's active kubeconfig without exposing
# the token in shell output or overriding a token the user supplied explicitly.
if [ -z "${ARGO_TOKEN:-}" ] && command -v kubectl >/dev/null 2>&1; then
    _K3S_TURING_PI_KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/config}"
    if [ -r "${_K3S_TURING_PI_KUBECONFIG}" ]; then
        _K3S_TURING_PI_ARGO_TOKEN="$(
            KUBECONFIG="${_K3S_TURING_PI_KUBECONFIG}" \
                kubectl config view --raw --minify \
                --output 'jsonpath={.users[0].user.token}' 2>/dev/null
        )"
        if [ -n "${_K3S_TURING_PI_ARGO_TOKEN}" ]; then
            export ARGO_TOKEN="Bearer ${_K3S_TURING_PI_ARGO_TOKEN}"
        fi
        unset _K3S_TURING_PI_ARGO_TOKEN
    fi
    unset _K3S_TURING_PI_KUBECONFIG
fi

if [ -z "${ARGO_HTTP1:-}" ]; then
    export ARGO_HTTP1=true
fi

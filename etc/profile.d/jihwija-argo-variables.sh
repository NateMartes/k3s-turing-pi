# Managed by jihwija for the Argo Workflows CLI.
# Use the cluster's Argo Server unless the user selected another endpoint.
if [ -z "${ARGO_SERVER:-}" ]; then
    export ARGO_SERVER="@ARGO_HOSTNAME@:443"
fi

# Argo Server client authentication expects the Kubernetes token with a
# "Bearer " prefix. Read it from the user's active kubeconfig without exposing
# the token in shell output or overriding a token the user supplied explicitly.
if [ -z "${ARGO_TOKEN:-}" ] && command -v kubectl >/dev/null 2>&1; then
    _JIHWIJA_KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/config}"
    if [ -r "${_JIHWIJA_KUBECONFIG}" ]; then
        _JIHWIJA_ARGO_TOKEN="$(
            KUBECONFIG="${_JIHWIJA_KUBECONFIG}" \
                kubectl config view --raw --minify \
                --output 'jsonpath={.users[0].user.token}' 2>/dev/null
        )"
        if [ -n "${_JIHWIJA_ARGO_TOKEN}" ]; then
            export ARGO_TOKEN="Bearer ${_JIHWIJA_ARGO_TOKEN}"
        fi
        unset _JIHWIJA_ARGO_TOKEN
    fi
    unset _JIHWIJA_KUBECONFIG
fi

if [ -z "${ARGO_HTTP1:-}" ]; then
    export ARGO_HTTP1=true
fi

# The Argo endpoint uses a private certificate at the external TLS proxy.
# Keep HTTPS encryption, but do not require the CLI to verify that certificate.
if [ -z "${ARGO_INSECURE_SKIP_VERIFY:-}" ]; then
    export ARGO_INSECURE_SKIP_VERIFY=true
fi

# Managed by k3s-turing-pi for the Argo Workflows CLI.
# Use the cluster's Argo Server unless the user selected another endpoint.
if [ -z "${ARGO_SERVER:-}" ]; then
    export ARGO_SERVER="argo.10.42.0.31.sslip.io:443"
fi

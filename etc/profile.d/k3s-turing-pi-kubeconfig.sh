# Managed by k3s-turing-pi for user kubeconfigs.
# Prefer each user's namespace-scoped kubeconfig over K3s's administrator config.
if [ -z "${KUBECONFIG:-}" ] && [ -r "${HOME}/.kube/config" ]; then
    export KUBECONFIG="${HOME}/.kube/config"
fi

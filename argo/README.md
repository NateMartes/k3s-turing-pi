# Argo Workflow Runner

The user-management plumbing scripts render the manifest template in this
directory to create an `argo-workflow-runner` service account in each user's
namespace. The account has namespace `admin` access so supplied workflows can
manage most namespaced resources, including Deployments, Jobs, Ingresses,
Secrets, Services, and PVCs. The binding does not grant access to resources in
other namespaces or to cluster-scoped resources. Explicit permissions to
create and patch `WorkflowTaskResult` resources are retained for Argo workflow
executor Pods. The user's existing
`<username>-user` service account also receives read-only access to
`ClusterWorkflowTemplate` resources so the Argo CLI can submit a shared
template through Argo Server.

Namespace `admin` is highly privileged. A workflow can read namespace Secrets,
replace other workloads, and create Pods with any settings accepted by cluster
admission policy. Apply an enforced Pod Security Standard or equivalent
admission policy before treating user namespaces as a security boundary.

## System installation

Argo Workflows is a first-class sysadmin service. The K3s Helm controller
installs the pinned `argo-workflows` chart from
[`sysadmin-services/argo-workflows.yaml`](../sysadmin-services/argo-workflows.yaml)
into `sysadmin-system` together with its Traefik Ingress and TLS certificate.
The chart is configured as a cluster-scoped installation so its controller can
process Workflows in every user namespace. It must not be changed to
`singleNamespace` mode.

Argo Server uses `client` authentication. Each request therefore uses the
caller's Kubernetes bearer token and RBAC permissions. Traefik terminates TLS
at the Ingress before forwarding traffic to the cluster-only Argo Server
Service. Client authentication requires Kubernetes 1.28 or newer. See the
official [Argo Server authentication documentation](https://argo-workflows.readthedocs.io/en/latest/argo-server-auth-mode/).

Configure `ARGO_HOSTNAME` in `etc/sysadmin-env`, install the configuration, and
deploy the complete sysadmin-services bundle:

```bash
sudo install -D -o root -g root -m 600 \
  ./etc/sysadmin-env /etc/k3s-turing-pi/sysadmin-env
sudo ./scripts/apply-sysadmin-services
```

Verify the Helm release, controller, server, client authentication, and
Ingress:

```bash
sudo k3s kubectl get helmchart argo-workflows --namespace kube-system
sudo k3s kubectl rollout status \
  deployment/argo-workflows-workflow-controller \
  --namespace sysadmin-system
sudo k3s kubectl rollout status deployment/argo-workflows-server \
  --namespace sysadmin-system
sudo k3s kubectl logs deployment/argo-workflows-server \
  --namespace sysadmin-system \
  --tail 100 | grep 'authModes="\[client\]"'
sudo k3s kubectl get ingress,certificate --namespace sysadmin-system
```

Install the generated private certificate in the hosts' shared trust store:

```bash
sudo ./scripts/trust-k3s-crets
```

If Argo is Ready at the configured `ARGO_HOSTNAME`, this command also updates
the workflow controller's `workflowDefaults`. Each newly created workflow
`main` container mounts the node's merged system CA bundle at
`/etc/ssl/certs/k3s-sysadmin-ca-bundle.pem`; common OpenSSL, curl, Git, Python,
Node.js, and AWS SDK CA environment variables use that file. Re-run the command
after changing a sysadmin-service certificate. Already-running workflow Pods
are unchanged. Runtimes with a separate non-PEM trust store, such as a JVM
application using its default JKS store, still need runtime-specific setup.

Use the Argo CLI's `--argo-http1` option with this standard HTTP Ingress. This
avoids requiring the Ingress route to support end-to-end gRPC over h2c.

### Migrating the old installation

If Argo was previously installed from the upstream release manifest, delete
its old namespace before applying the sysadmin-services bundle:

```bash
sudo k3s kubectl delete namespace argo --ignore-not-found
```

Deleting the namespace removes every namespaced Deployment, Service,
ServiceAccount, Role, RoleBinding, ConfigMap, Secret, and Pod in it. It does not
remove cluster-scoped resources. If the old installation came from Argo's
official `install.yaml`, remove its now-unused cluster RBAC and priority class:

```bash
sudo k3s kubectl delete clusterrolebinding \
  argo-binding argo-server-binding \
  --ignore-not-found
sudo k3s kubectl delete clusterrole \
  argo-aggregate-to-admin \
  argo-aggregate-to-edit \
  argo-aggregate-to-view \
  argo-cluster-role \
  argo-server-cluster-role \
  --ignore-not-found
sudo k3s kubectl delete priorityclass workflow-controller \
  --ignore-not-found
```

Do not delete the Argo CRDs or existing `ClusterWorkflowTemplate` objects. The
Helm release adopts and updates the CRDs, and the shared templates remain
available to users. The cleanup above also leaves the repository's per-user
runner RBAC intact.

### Create the user's namespace

The workflow runner is installed after the user's namespace exists. The main
`create-user` command performs both steps automatically. When using the
plumbing commands directly, create the namespace first or use the repository's
namespace installer:

```bash
sudo ./scripts/plumbing-scripts/install-k3s-namespace --username bob
```

The namespace installer also creates the user's `~/.kube/config`. Before
creating users, install the repository's system-wide profiles once so `kubectl`
selects that namespace-scoped config and the Argo CLI selects the cluster's
Argo Server on login:

```bash
sudo install -D -o root -g root -m 644 \
  ./etc/profile.d/k3s-turing-pi-kubeconfig.sh \
  /etc/profile.d/k3s-turing-pi-kubeconfig.sh
sudo install -D -o root -g root -m 644 \
  ./etc/profile.d/k3s-turing-pi-argo-variables.sh \
  /etc/profile.d/k3s-turing-pi-argo-variables.sh
```

### Deploy the workflow runner

Pass both the Linux username and target namespace explicitly:

```bash
sudo ./scripts/plumbing-scripts/install-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

This creates the following namespaced resources:

- `ServiceAccount/argo-workflow-runner`
- `Role/argo-workflow-runner`
- `RoleBinding/argo-workflow-runner`
- `RoleBinding/argo-workflow-runner-namespace-admin`

It also creates the shared
`ClusterRole/argo-workflow-template-reader` and a per-user
`ClusterRoleBinding/<username>-argo-workflow-template-reader`. The role only
grants `get` access to cluster workflow templates; it cannot create, update, or
delete them. The shared ClusterRole remains when one user's runner is removed
because other users may still depend on it.

The resources use `app.kubernetes.io/managed-by: k3s-turing-pi` to identify
this repository's user-management tooling as their manager, and carry the
managed Linux username in the `k3s-turing-pi.io/username` annotation.

The fixed name is intentional. Service accounts in different namespaces are
different Kubernetes identities, so `bob-namespace/argo-workflow-runner` and
`alice-namespace/argo-workflow-runner` do not share permissions. Keeping the
same name lets one shared `ClusterWorkflowTemplate` work in every user
namespace.

The main user-management commands install and remove the runner automatically.
To remove only the runner without deleting its namespace, run:

```bash
sudo ./scripts/plumbing-scripts/uninstall-argo-workflow-runner \
  --username bob \
  --namespace bob-namespace
```

## Use in a workflow

Set the service account in a `Workflow`, `WorkflowTemplate`, or
`ClusterWorkflowTemplate`:

```yaml
spec:
  serviceAccountName: argo-workflow-runner
```

The name resolves in the namespace containing the submitted `Workflow`. A
workflow in `bob-namespace` therefore uses
`system:serviceaccount:bob-namespace:argo-workflow-runner`.

## Verify

Set `USERNAME` and `WORKFLOW_NAMESPACE` for the user whose runner was
installed:

```bash
USERNAME=bob
WORKFLOW_NAMESPACE="${USERNAME}-namespace"

sudo k3s kubectl get serviceaccount argo-workflow-runner \
  --namespace "${WORKFLOW_NAMESPACE}"

sudo k3s kubectl auth can-i create workflowtaskresults.argoproj.io \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"

sudo k3s kubectl auth can-i patch workflowtaskresults.argoproj.io \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"

sudo k3s kubectl auth can-i create services \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"

sudo k3s kubectl auth can-i create ingresses.networking.k8s.io \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"

sudo k3s kubectl auth can-i create deployments.apps \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"

sudo k3s kubectl auth can-i get clusterworkflowtemplates.argoproj.io \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:${USERNAME}-user"
```

All six authorization checks should return `yes`.

## Example workflow

The repository includes a three-minute Flask API example at
`argo/flask-hello-world-argo`. Follow
[Deploying an Argo Workflow](../docs/DEPLOYING_ARGO_WORKFLOW.md) to install its
shared `ClusterWorkflowTemplate`, submit it in a user namespace, and call the
API.

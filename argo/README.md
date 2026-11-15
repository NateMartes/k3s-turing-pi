# Argo Workflow Runner

The user-management plumbing scripts render the manifest template in this
directory to create an `argo-workflow-runner` service account in each user's
namespace. The account has the minimum namespace-scoped permissions required
by Argo workflow executor Pods: it can create and patch `WorkflowTaskResult`
resources. It can also create, inspect, and delete Services for supplied
workflows that expose temporary endpoints, but it cannot create Deployments,
Secrets, or resources in another namespace. The user's existing
`<username>-user` service account also receives read-only access to
`ClusterWorkflowTemplate` resources so the Argo CLI can submit a shared
template directly.

## Setup

### 1. Install Argo Workflows

Choose a stable version from the official
[Argo Workflows releases](https://github.com/argoproj/argo-workflows/releases/)
page. Set that version below, create the Argo namespace, and install the
cluster-scoped release manifest:

```bash
ARGO_WORKFLOWS_VERSION=v4.1.6

sudo k3s kubectl create namespace argo
sudo k3s kubectl apply --server-side \
  --namespace argo \
  --filename "https://github.com/argoproj/argo-workflows/releases/download/${ARGO_WORKFLOWS_VERSION}/install.yaml"
```

If the namespace already exists, the `create namespace` command reports
`AlreadyExists` and setup can continue. Argo Workflows v4 requires server-side
apply for its full CRDs because a client-side last-applied annotation can exceed
Kubernetes' annotation size limit.

Wait for the controller and server, then inspect their Pods:

```bash
sudo k3s kubectl rollout status deployment/workflow-controller \
  --namespace argo
sudo k3s kubectl rollout status deployment/argo-server \
  --namespace argo
sudo k3s kubectl get pods --namespace argo
```

### 2. Create the user's namespace

The workflow runner is installed after the user's namespace exists. The main
`create-user` command performs both steps automatically. When using the
plumbing commands directly, create the namespace first or use the repository's
namespace installer:

```bash
sudo ./scripts/plumbing-scripts/install-k3s-namespace --username bob
```

The namespace installer also creates the user's `~/.kube/config`. Before
creating users, install the repository's system-wide profile once so `kubectl`
selects that namespace-scoped config on login:

```bash
sudo install -D -o root -g root -m 644 \
  ./etc/profile.d/k3s-turing-pi-kubeconfig.sh \
  /etc/profile.d/k3s-turing-pi-kubeconfig.sh
```

### 3. Deploy the workflow runner

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

sudo k3s kubectl auth can-i get clusterworkflowtemplates.argoproj.io \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:${USERNAME}-user"
```

All four authorization checks should return `yes`.

Workflows that create Kubernetes resources through Argo resource templates
need additional, narrowly scoped permissions for those resource types. Add
those permissions only when a supplied workflow requires them.

## Example workflow

The repository includes a three-minute Flask API example at
`argo/flask-hello-world-argo`. Follow
[Deploying an Argo Workflow](../docs/DEPLOYING_ARGO_WORKFLOW.md) to install its
shared `ClusterWorkflowTemplate`, submit it in a user namespace, and call the
API.

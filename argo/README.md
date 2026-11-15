# Argo Workflow Runner

This Kustomize bundle creates an `argo-workflow-runner` service account with
the minimum namespace-scoped permissions required by Argo workflow executor
Pods. It can create and patch `WorkflowTaskResult` resources, but it cannot
create Deployments, Services, Secrets, or resources in another namespace.

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

### 2. Select the workflow namespace

The target namespace must exist. The bundle targets the `default` namespace
initially. To use another namespace, change the `namespace` value in
`kustomization.yaml` before applying it.

### 3. Deploy the workflow runner

From the repository root, deploy the bundle with K3s:

```bash
sudo k3s kubectl apply -k argo
```

If this machine exposes K3s through the regular `kubectl` command instead, use:

```bash
sudo kubectl apply -k argo
```

Create a separate instance of this bundle in every namespace that will run
workflows. A service account is namespaced, so an account deployed in `default`
cannot be used by a workflow running in another namespace.

## Use in a workflow

Set the service account in a `Workflow`, `WorkflowTemplate`, or
`ClusterWorkflowTemplate`:

```yaml
spec:
  serviceAccountName: argo-workflow-runner
```

The name resolves in the namespace containing the submitted `Workflow`.

## Verify

Set `WORKFLOW_NAMESPACE` to the namespace configured in `kustomization.yaml`:

```bash
WORKFLOW_NAMESPACE=default

sudo k3s kubectl get serviceaccount argo-workflow-runner \
  --namespace "${WORKFLOW_NAMESPACE}"

sudo k3s kubectl auth can-i create workflowtaskresults.argoproj.io \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"

sudo k3s kubectl auth can-i patch workflowtaskresults.argoproj.io \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --as "system:serviceaccount:${WORKFLOW_NAMESPACE}:argo-workflow-runner"
```

Both authorization checks should return `yes`.

Workflows that create Kubernetes resources through Argo resource templates
need additional, narrowly scoped permissions for those resource types. Add
those permissions only when a supplied workflow requires them.

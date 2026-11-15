# Deploying an Argo Workflow

This example installs a shared `ClusterWorkflowTemplate`, submits it into a
user namespace, and starts a small Flask API that returns `Hello <message>`.
The API runs for three minutes, exits successfully, and Argo removes its
temporary Service and completed Pod.

## Steps

### 1. Check the prerequisites

Run these commands from the repository root. Confirm that the Argo controller
is running, the Argo CLI is installed, and the target namespace contains
`argo-workflow-runner`:

```bash
USERNAME=martesn
WORKFLOW_NAMESPACE="${USERNAME}-namespace"

sudo kubectl get deployment workflow-controller --namespace argo
argo version --client
kubectl get serviceaccount argo-workflow-runner \
  --namespace "${WORKFLOW_NAMESPACE}"
kubectl auth can-i get clusterworkflowtemplates.argoproj.io
```

The final command should return `yes`. For users created before the current
runner permissions were added, an administrator can rerun
`scripts/plumbing-scripts/install-argo-workflow-runner` for that user.

### 2. Install the shared Flask workflow template

An administrator installs the cluster-scoped template once:

```bash
sudo kubectl apply --server-side \
  --filename argo/flask-hello-world-argo
```

### 3. Submit the workflow

Submit the shared template, pass the message Flask should return, and stream
its logs:

```bash
argo submit \
  --from clusterworkflowtemplate/flask-hello-world \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --parameter 'message=Turing Pi' \
  --log
```

### 4. Use the printed URL

The workflow creates a temporary `NodePort` Service. Kubernetes selects an
available port from the cluster's configured NodePort range, and the workflow
prints everything needed to use it:

```text
Flask workflow is ready
Workflow: flask-hello-world-abcde
Response: Hello Turing Pi
URL: http://192.0.2.10:30123/
Try: curl http://192.0.2.10:30123/
Lifetime: 180 seconds
```

Run the printed `curl` command from another terminal before the lifetime ends.
After three minutes, Flask exits and the workflow removes its Service and Pod.
The Workflow record remains with status `Succeeded`.

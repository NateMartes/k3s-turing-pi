# Deploying an Argo Workflow

This example installs a shared `ClusterWorkflowTemplate`, submits it into a
user namespace, and starts a small Flask API that returns `Hello <message>`.
The API runs for three minutes, exits successfully, and Argo removes its
temporary Service. Completed workflow Pods remain available for log streaming
for 30 seconds after the workflow finishes and are then removed automatically.

## Steps

### 1. Check the prerequisites

Run these commands from the repository root. Confirm that the Argo controller
and Argo Server are running, Argo Server uses `client` authentication, the
Argo CLI is installed, the server endpoint configured during Argo setup is
reachable, and the target namespace contains `argo-workflow-runner`:

```bash
USERNAME=martesn
WORKFLOW_NAMESPACE="${USERNAME}-namespace"
ARGO_HOSTNAME="argo.10.42.0.31.sslip.io"

sudo kubectl get deployment argo-workflows-workflow-controller \
  --namespace jihwija-system
sudo kubectl get deployment argo-workflows-server \
  --namespace jihwija-system
sudo kubectl logs deployment/argo-workflows-server \
  --namespace jihwija-system \
  --tail 100 | grep 'authModes="\[client\]"'
curl --silent --show-error \
  --output /dev/null \
  "https://${ARGO_HOSTNAME}/"
argo version --client
kubectl get serviceaccount argo-workflow-runner \
  --namespace "${WORKFLOW_NAMESPACE}"
kubectl auth can-i get clusterworkflowtemplates.argoproj.io
```

The log check should print a startup line containing `authModes="[client]"`,
and the final command should return `yes`. If Argo Server is not in client
mode, follow the client-authentication setup in
[Argo Workflow Runner](../argo/README.md#system-installation). If the endpoint
check fails, verify the Argo Ingress and certificate in `jihwija-system` as
described in that setup.
For users created before the current runner permissions were added, an
administrator can rerun
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
  --argo-http1 \
  --from clusterworkflowtemplate/flask-hello-world \
  --namespace "${WORKFLOW_NAMESPACE}" \
  --parameter 'message=Turing Pi' \
  --log
```

`ARGO_SERVER` must be set for this command to use Argo Server. The system-wide
Argo variables profile configures it and derives `ARGO_TOKEN` from the active
user in the user's kubeconfig. Without `ARGO_SERVER`, the CLI uses direct
Kubernetes API mode and Argo CLI v4.1.6 cannot resolve this cluster workflow
template during submission. Argo Server enforces the Kubernetes RBAC
permissions associated with the exported bearer token.

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
After three minutes, Flask exits and the workflow removes its Service. Argo
keeps the workflow Pods for another 30 seconds so the CLI can finish streaming
their logs, then removes them. The Workflow record remains with status
`Succeeded`.

The Jihwija Argo installation assigns small default CPU and memory resources
to Argo's generated executor containers. The example also assigns resources to
the generated `main` containers used by its Kubernetes resource templates.
These settings are required because every user namespace quota requires CPU
and memory requests and limits on every container.

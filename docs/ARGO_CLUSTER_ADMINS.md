# Argo Cluster Workflow Template Administrators

Use [`example.yml`](../argo/clusterworkflowadmins/example.yml) to allow an existing system user to create,
edit, and delete shared Argo `ClusterWorkflowTemplate` resources. The manifest
grants access to the user's existing `<username>-user` service account in the
`<username>-namespace` namespace.

This is a cluster-wide permission. A user with this role can change or remove
templates used by every namespace, so grant it only to trusted administrators.

## Grant access

The user must already have been created with this repository's user-management
scripts. Replace every occurrence of `USERNAME` in the example with the user's
Linux username and apply the rendered manifest. For example, to grant access to
`bob` without changing the checked-in example:

```bash
sed 's/USERNAME/bob/g' argo/clusterworkflowadmins/example.yml \
  | sudo k3s kubectl apply -f -
```

The command creates or updates one shared
`ClusterRole/argo-cluster-workflow-template-admin` and creates a user-specific
`ClusterRoleBinding/bob-argo-cluster-workflow-template-admin`.

Verify that the user's Kubernetes identity can create and delete cluster
workflow templates:

```bash
sudo k3s kubectl auth can-i create clusterworkflowtemplates.argoproj.io \
  --as system:serviceaccount:bob-namespace:bob-user

sudo k3s kubectl auth can-i delete clusterworkflowtemplates.argoproj.io \
  --as system:serviceaccount:bob-namespace:bob-user
```

Both commands should return `yes`. After signing in as that user, the user can
manage templates with the Argo CLI, for example:

```bash
argo cluster-template create ./cluster-workflow-template.yml --argo-http1
argo cluster-template delete my-cluster-template --argo-http1
```

## Revoke access

Delete only the user's binding. For example, to revoke `bob`:

```bash
sudo k3s kubectl delete clusterrolebinding \
  bob-argo-cluster-workflow-template-admin
```

Keep the shared `argo-cluster-workflow-template-admin` ClusterRole if any other
administrator uses it. Removing the binding does not delete any existing
`ClusterWorkflowTemplate` resources, and it does not remove the user's normal
read-only template access installed by the user-management scripts.

Confirm that the elevated permissions are gone:

```bash
sudo k3s kubectl auth can-i create clusterworkflowtemplates.argoproj.io \
  --as system:serviceaccount:bob-namespace:bob-user

sudo k3s kubectl auth can-i delete clusterworkflowtemplates.argoproj.io \
  --as system:serviceaccount:bob-namespace:bob-user
```

Both commands should now return `no`.

---
title: JIHWIJA-ARGO-TEMPLATE-ADMIN
section: 7
header: Jihwija Manual
footer: Jihwija 0.1.0
man-name: jihwija-argo-template-admin
description: manage elevated access to shared Argo workflow templates
---

# Argo Cluster Workflow Template Administrators

Use the Jihwija privilege commands to allow an existing managed user to create,
edit, and delete shared Argo `ClusterWorkflowTemplate` resources. The
`argo-template-admin` privilege grants access to the user's existing
`<username>-user` service account in the `<username>-namespace` namespace.

This is a cluster-wide permission. A user with this role can change or remove
templates used by every namespace, so grant it only to trusted administrators.

## Grant access

The Linux user, managed Kubernetes namespace, and user service account must
already exist. Grant access to `bob` with:

```bash
sudo jihwija grant user bob argo-template-admin
```

Maintainers can run the same operation directly through its plumbing command:

```bash
sudo ./scripts/plumbing-scripts/grant-user-privilege.py \
  bob argo-template-admin
```

The operation is idempotent and can be rerun to reconcile the role and binding.

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

Revoke access from `bob` with:

```bash
sudo jihwija revoke user bob argo-template-admin
```

Or run the plumbing command directly:

```bash
sudo ./scripts/plumbing-scripts/revoke-user-privilege.py \
  bob argo-template-admin
```

Revocation is idempotent and works even if the Linux user or namespace has
already been removed. It deletes only the user's binding. The shared
`argo-cluster-workflow-template-admin` ClusterRole remains for other
administrators. Removing the binding does not delete existing
`ClusterWorkflowTemplate` resources or the user's normal read-only template
access.

Uninstalling the user's Argo workflow runner also revokes this privilege. Final
managed-user removal performs the same cleanup defensively and stops without
deleting the Linux account if Kubernetes privilege cleanup fails.

Confirm that the elevated permissions are gone:

```bash
sudo k3s kubectl auth can-i create clusterworkflowtemplates.argoproj.io \
  --as system:serviceaccount:bob-namespace:bob-user

sudo k3s kubectl auth can-i delete clusterworkflowtemplates.argoproj.io \
  --as system:serviceaccount:bob-namespace:bob-user
```

Both commands should now return `no`.

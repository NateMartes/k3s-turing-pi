---
title: JIHWIJA-OBSERVABILITY
section: 7
header: Jihwija Manual
footer: Jihwija
man-name: jihwija-observability
description: operate Jihwija Loki, Grafana, Mimir, and Alloy services
---

# Jihwija Observability Stack

Jihwija provides four independent, default-enabled services in the
`jihwija-system` namespace:

- **Loki** stores Kubernetes Pod and container logs for seven days in an 11Gi
  retained `local-path` volume.
- **Mimir** uses the pinned upstream `mimir-distributed` Helm chart. Its
  gateway, distributor, ingester, query path, store gateway, compactor, Kafka,
  and MinIO workloads are single replicas placed together on the service node.
  MinIO has an 8Gi retained `local-path` volume for fourteen days of metric
  blocks; the ingester, Kafka, store gateway, and compactor use additional 1Gi
  retained claims for their WAL, ingest buffer, and working data.
- **Grafana** uses a 1Gi retained volume for SQLite and exposes the only public
  observability ingress. Its Loki and Mimir datasources have stable UIDs, and
  Jihwija provisions dashboards for cluster health, resource utilization,
  workload status, restarts, logs, and events. Dashboard source files live in
  the top-level `grafana/` directory, with one complete dashboard per JSON
  file. Deployment validates those files and renders each as a labeled
  ConfigMap for Grafana's dashboard sidecar.
- **Alloy** collects telemetry. Per-node DaemonSets tail Kubernetes container
  log files and collect host metrics. A singleton reads Kubernetes events, and
  clustered collectors scrape kubelet/cAdvisor, kube-state-metrics, and
  annotated workloads. Node Exporter runs on every node.

All central workloads use the `jihwija-services=true` node selector. Per-node
collectors tolerate control-plane, GPU, and other taints so existing and newly
joined K3s nodes are covered without installing a host package or running a
separate Ansible playbook.

## Configure and deploy

Set Grafana's hostname and administrator password before deployment:

```bash
sudo jihwija set hostname grafana grafana.10.42.0.31.sslip.io
sudo jihwija set secret GRAFANA_ADMIN_PASSWORD
sudo jihwija deploy
```

Each service can be managed separately:

```bash
sudo jihwija disable service loki
sudo jihwija enable service loki
sudo jihwija disable service grafana
sudo jihwija enable service grafana
sudo jihwija disable service mimir
sudo jihwija enable service mimir
sudo jihwija disable service alloy
sudo jihwija enable service alloy
```

There is no `lgm`, `lgtm`, or `observability` composite service. Disabling a
backend does not rewrite the other services. Alloy remains ready and retries
the unavailable Loki or Mimir destination; destination connection errors in
its logs are expected in that state. Grafana retains both datasource
definitions and reports the disabled backend as unavailable.

## Collection boundary

Alloy only pulls telemetry:

- Kubernetes Pod and container logs from the node log filesystem.
- Kubernetes events from the API.
- kubelet/cAdvisor, kube-state-metrics, Node Exporter, and annotated workload
  metrics.

Application Observability, auto-instrumentation, OTLP receivers, Prometheus
remote-write receivers, Loki push receivers, receiver Services, syslog, host
journals, and arbitrary host file collection are explicitly disabled. Tempo
and traces are not installed.

## Storage and access

The deployment is a small-cluster, non-HA design. Mimir has multiple processes,
but all of its single-replica workloads run on the same service node. Retention
is a ceiling: Loki or Mimir can fill its local volumes sooner under heavy
ingestion. PVCs carry Helm retention annotations and StatefulSet claims use
retained policies so disabling or upgrading a service does not discard stored
data.

Loki and Mimir use internal ClusterIP Services. Namespace NetworkPolicies only
allow Alloy to write to them and Grafana to query them. Grafana is served by
Traefik over TLS and accepts ingress from Traefik in `kube-system`.

Inspect the service workloads and collector placement with:

```bash
sudo k3s kubectl get pods -n jihwija-system -o wide
sudo k3s kubectl get daemonsets -n jihwija-system
sudo k3s kubectl logs -n jihwija-system -l jihwija.io/service=alloy --tail=100
```

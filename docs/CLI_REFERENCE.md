---
title: JIHWIJA
section: 1
header: Jihwija Manual
footer: Jihwija 0.1.0
man-name: jihwija
description: command-line interface and native plumbing command reference
---

# Jihwija CLI Command Reference

The `jihwija` CLI provides verb-first routes to the directly executable
playbooks and Python plumbing scripts in this repository. Run `jihwija
--help` to list commands, or `jihwija COMMAND --help` for the options accepted
by a specific command.

## Cluster and Platform Commands

| Action | Jihwija CLI Command | Native Manual Command |
| :--- | :--- | :--- |
| **Initialize Inventory** | `sudo jihwija init [FILE]` | Edit `ansible/inventory.yml` and `group_vars/all.yml`, or run `sudo ./scripts/plumbing-scripts/init-cluster.py [FILE]` |
| **Install K3s** | `sudo jihwija install k3s` | `cd ansible && ansible-playbook -i inventory.yml setup-k3s.yml` |
| **Uninstall K3s** | `sudo jihwija uninstall k3s` | `cd ansible && ansible-playbook -i inventory.yml remove-k3s.yml` |
| **Restart K3s** | — | `cd ansible && ansible-playbook -i inventory.yml restart-k3s.yml` |
| **Default Gateway** | — | `cd ansible && ansible-playbook -i inventory.yml setup-default-gateway.yml` |
| **Distribute Hostnames** | — | `cd ansible && ansible-playbook -i inventory.yml distribute-hostnames.yml` |
| **Deploy Services** | `sudo jihwija deploy` | `sudo ./scripts/plumbing-scripts/deploy-services.py` |
| **Distribute CA Trust** | `sudo jihwija trust certs` | `sudo ./scripts/plumbing-scripts/trust-k3s-certs.py` |
| **Taint GPU Nodes** | — | `sudo ./scripts/plumbing-scripts/k3s-taint-gpu-nodes.py` |
| **Untaint GPU Nodes** | — | `sudo ./scripts/plumbing-scripts/k3s-untaint-gpu-nodes.py` |
| **Add Worker Node** | `sudo jihwija add node <name> <ip>` | `sudo ./scripts/plumbing-scripts/add-node.py <name> <ip>` |
| **Remove Worker Node** | `sudo jihwija remove node <name>` | `sudo ./scripts/plumbing-scripts/remove-node.py <name>` |
| **Set Service Hostname** | `sudo jihwija set hostname <service> <fqdn>` | `sudo ./scripts/plumbing-scripts/set-hostname.py <service> <fqdn>` |
| **Set Service Secret** | `sudo jihwija set secret <key>` | `sudo ./scripts/plumbing-scripts/set-secret.py <key>` |
| **Enable Quotas** | `sudo jihwija enable quotas <path>` | `sudo ./scripts/plumbing-scripts/enable-quotas.py <path>` |
| **Disable Quotas** | `sudo jihwija disable quotas <path>` | `sudo ./scripts/plumbing-scripts/disable-quotas.py <path>` |

## Managed User Commands

| Action | Jihwija CLI Command | Native Manual Command |
| :--- | :--- | :--- |
| **Provision User (Interactive)** | `sudo jihwija add user [name]` | `sudo ./scripts/plumbing-scripts/create-user.py -u [name]` |
| **Provision User (Automated)** | `sudo jihwija add user [name] --quota 10GB ...` | `sudo ./scripts/plumbing-scripts/create-user.py -u [name] --quota 10GB ...` |
| **Provision User (No Quotas)** | `sudo jihwija add user [name] --no-quota` | `sudo ./scripts/plumbing-scripts/create-user.py -u [name] --no-quota` |
| **Provision User (Selective)** | `sudo jihwija add user [name] --only <list>` | `sudo ./scripts/plumbing-scripts/create-user.py -u [name] --only <list>` |
| **Change User Password** | `sudo jihwija set user password [name]` | `sudo ./scripts/plumbing-scripts/change-user-password.py -u [name]` |
| **Change User Quota** | `sudo jihwija set user quota [name] [flags]` | `sudo ./scripts/plumbing-scripts/change-user-quota.py -u [name] [flags]` |
| **Remove User (Interactive)** | `sudo jihwija remove user [name]` | `sudo ./scripts/plumbing-scripts/remove-user.py -u [name]` |
| **Remove User (Purge Data)** | `sudo jihwija remove user [name] --purge-data --yes` | `sudo ./scripts/plumbing-scripts/remove-user.py -u [name] --purge-data --yes` |
| **Remove User (Selective)** | `sudo jihwija remove user [name] --only <list>` | `sudo ./scripts/plumbing-scripts/remove-user.py -u [name] --only <list>` |
| **Grant Argo Template Administration** | `sudo jihwija grant user <name> argo-template-admin` | `sudo ./scripts/plumbing-scripts/grant-user-privilege.py <name> argo-template-admin` |
| **Revoke Argo Template Administration** | `sudo jihwija revoke user <name> argo-template-admin` | `sudo ./scripts/plumbing-scripts/revoke-user-privilege.py <name> argo-template-admin` |

## Component Plumbing Commands

These lower-level component commands do not currently have dedicated CLI
routes. They remain supported for maintainers and automation.

| Action | Native Manual Command |
| :--- | :--- |
| **Install Docker Rootless** | `sudo ./scripts/plumbing-scripts/install-docker-rootless.py -u [name]` |
| **Uninstall Docker Rootless** | `sudo ./scripts/plumbing-scripts/uninstall-docker-rootless.py -u [name]` |
| **Install Portainer Agent** | `sudo ./scripts/plumbing-scripts/install-portainer-agent.py -u [name] -H <host>` |
| **Uninstall Portainer Agent** | `sudo ./scripts/plumbing-scripts/uninstall-portainer-agent.py -u [name]` |
| **Install K3s Namespace** | `sudo ./scripts/plumbing-scripts/install-k3s-namespace.py -u [name]` |
| **Uninstall K3s Namespace** | `sudo ./scripts/plumbing-scripts/uninstall-k3s-namespace.py -u [name]` |
| **Set K3s Namespace Quota** | `sudo ./scripts/plumbing-scripts/set-k3s-quota.py -u [name]` |
| **Install Argo Runner** | `sudo ./scripts/plumbing-scripts/install-argo-workflow-runner.py -u [name] -n [namespace]` |
| **Uninstall Argo Runner** | `sudo ./scripts/plumbing-scripts/uninstall-argo-workflow-runner.py -u [name] -n [namespace]` |
| **Install Harbor Account** | `sudo ./scripts/plumbing-scripts/install-harbor-account.py -u [name] -H <host>` |
| **Uninstall Harbor Account** | `sudo ./scripts/plumbing-scripts/uninstall-harbor-account.py -u [name] -H <host>` |
| **Set Harbor Password** | `sudo ./scripts/plumbing-scripts/set-harbor-password.py -u [name] -H <host>` |
| **Set Harbor Quota** | `sudo ./scripts/plumbing-scripts/set-harbor-quota.py -u [name] -H <host>` |
| **Install Rancher Account** | `sudo ./scripts/plumbing-scripts/install-rancher-account.py -u [name] -H <host>` |
| **Uninstall Rancher Account** | `sudo ./scripts/plumbing-scripts/uninstall-rancher-account.py -u [name] -H <host>` |
| **Set Rancher Password** | `sudo ./scripts/plumbing-scripts/set-rancher-password.py -u [name] -H <host>` |
| **Install Portainer Account** | `sudo ./scripts/plumbing-scripts/install-portainer-account.py -u [name] -H <host>` |
| **Uninstall Portainer Account** | `sudo ./scripts/plumbing-scripts/uninstall-portainer-account.py -u [name] -H <host>` |

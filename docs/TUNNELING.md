# Tunneling to the Web Services

Use an SSH tunnel when your computer can reach an SSH host in the cluster but
cannot reach the cluster network directly. One dynamic tunnel can provide
access to Rancher, Harbor, and Portainer.

The tunnel creates a local SOCKS5 proxy. Your browser sends its web requests
through the SSH host. The SSH host then resolves the service hostnames and
connects to the cluster ingress.

## Prerequisites

You need:

- SSH access to a host that can reach the cluster network.
- An OpenSSH client on your computer.
- The service hostnames from `etc/sysadmin-env`.
- A browser that supports a SOCKS5 proxy.

The SSH host does not have to run the web services. It only needs network
access to their configured hostnames on TCP port 443.

## 1. Start the tunnel

Run this command on your computer:

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -D 127.0.0.1:1080 \
  <username>@<ssh-host>
```

Replace `<ssh-host>` with the address of a reachable cluster host. The command
does not open a remote shell. It remains active while the tunnel is active.
Keep this terminal open. Press `Ctrl+C` when you want to close the tunnel.

You ought to probably tunnnel into your controller node, like your sysadmin
service node.

## 2. Configure a browser

Configure the browser to use these proxy settings:

- Proxy type: SOCKS5
- Host: `127.0.0.1`
- Port: `1080`
- DNS: Resolve hostnames through the proxy

You must enable proxy DNS. Without it, your computer can try to resolve or
connect to a private cluster address directly.

### Firefox

1. Open **Settings**.
3. Select **Privacy and security**.
4. Select **Advanced settings** after **Connection and software security**
5. Select **Configure proxy** under **Proxy settings** 
4. Select **Manual proxy configuration**.
5. Set **SOCKS Host** to `127.0.0.1` and **Port** to `1080`.
6. Select **SOCKS v5**.
7. Select **Proxy DNS when using SOCKS v5**.
8. Save the settings.

These settings affect the Firefox profile until you restore its previous proxy
settings.

### Chromium or Google Chrome

Start a separate browser profile from the same computer:

```bash
chromium \
  --user-data-dir="${TMPDIR:-/tmp}/k3s-tunnel-browser" \
  --proxy-server="socks5://127.0.0.1:1080"
```

Use `google-chrome` instead of `chromium` if that is the installed command.
Close this browser window before you close the tunnel.

## 3. Open the services

Open each service with its configured hostname:

- Harbor: `https://<HARBOR_HOSTNAME>`
- Portainer: `https://<PORTAINER_HOSTNAME>`
- Rancher: `https://<RANCHER_HOSTNAME>`

Get the actual values from `etc/sysadmin-env`. Keep the `https://` scheme and
do not replace the service hostname with `localhost`. The ingress uses the
hostname to select a service and its TLS certificate.

## Certificate trust

The SSH tunnel encrypts traffic between your computer and the SSH host. It does
not add the cluster's private certificate authorities to your browser.

The repository's `scripts/trust-k3s-crets` command installs those authorities
on the computer where you run the command. If you use the tunnel from a
different computer, install the same private authorities on that computer
before you enter credentials. Do not ignore a certificate warning unless you
have independently verified the certificate.

## Troubleshooting

### The SSH command reports that port 1080 is in use

Select a different local port, such as `1081`, in both the SSH command and the
browser proxy settings.

### The browser cannot find a service hostname

Check that the browser resolves DNS through the SOCKS5 proxy. Then connect to
the SSH host and check the configured hostname:

```bash
getent hosts <RANCHER_HOSTNAME>
```

Repeat the check for Harbor or Portainer as necessary.

### The browser reports a proxy connection failure

Check that the SSH command is still active. You can also inspect the local
listening port from another terminal:

```bash
ss -ltn 'sport = :1080'
```

### The browser opens the wrong service

Use the full configured hostname in the URL. Do not use the SSH host's address,
the ingress address, or `localhost` as the web address.

#!/usr/bin/env python3
from __future__ import annotations

import getpass
import json
import os
import pwd
import grp
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

MANAGED_MARKER = "# Managed by sysadmin. Created by {}"
DEFAULT_RANCHER_HOST = os.environ.get("RANCHER_HOSTNAME")
DEFAULT_PORTAINER_HOST = os.environ.get("PORTAINER_HOSTNAME")

def get_marker(service):
    return MANAGED_MARKER.format(service)

def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)

def require_hostname(value: Optional[str], variable: str) -> str:
    if value:
        return value
    die(
        f"{variable} is not set. Source sysadmin-env or provide --hostname."
    )

def info(message: str) -> None:
    print(f"==> {message}")

def current_username() -> str:
    return pwd.getpwuid(os.getuid()).pw_name

def get_user(username: Optional[str] = None):
    username = username or current_username()
    try:
        return pwd.getpwnam(username)
    except KeyError:
        die(f"Linux user '{username}' does not exist.")

def require_root_for_other_user(username: str) -> None:
    if username != current_username() and os.geteuid() != 0:
        die(f"Managing another user requires root. Re-run with sudo.")

def require_root() -> None:
    if os.geteuid() != 0:
        die("This operation requires root. Re-run with sudo.")

def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    text: bool = True,
    env: Optional[dict[str, str]] = None,
    input_data: Optional[str] = None,
) -> subprocess.CompletedProcess:
    kwargs = {
        "check": check,
        "text": text,
        "env": env,
        "input": input_data,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    return subprocess.run(cmd, **kwargs)

def run_as_target_user(
    username: str,
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
):
    """
    Run only the commands that actually need the target user's UID.

    The overall installer still runs as root.
    """

    user = get_user(username)

    runtime_dir = f"/run/user/{user.pw_uid}"

    env_command = [
        "runuser",
        "-u",
        username,
        "--",
        "env",
        "-i",
        f"HOME={user.pw_dir}",
        f"USER={username}",
        f"LOGNAME={username}",
        f"XDG_RUNTIME_DIR={runtime_dir}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir}/bus",
        (
            f"PATH={user.pw_dir}/bin:"
            "/usr/local/sbin:"
            "/usr/local/bin:"
            "/usr/sbin:"
            "/usr/bin:"
            "/sbin:"
            "/bin"
        ),
        *command,
    ]

    return run(
        env_command,
        check=check,
        capture=capture,
    )

def which_or_die(name: str) -> str:
    path = shutil.which(name)
    if not path:
        die(f"Required command '{name}' was not found in PATH.")
    return path

def user_env(username: str) -> dict[str, str]:
    u = get_user(username)
    env = os.environ.copy()
    env.update({
        "HOME": u.pw_dir,
        "USER": username,
        "LOGNAME": username,
        "XDG_RUNTIME_DIR": f"/run/user/{u.pw_uid}",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{u.pw_uid}/bus",
    })
    return env

def determine_username(argument: str | None) -> str:
    if argument:
        return argument

    # If manually invoked through sudo, this is more useful than returning root.
    sudo_user = os.environ.get("SUDO_USER")

    if sudo_user and sudo_user != "root":
        return sudo_user

    die(
        "A target username is required when running as root.\n"
        "Example: install-docker-rootless -u bob"
    )

def ensure_user_manager(username: str) -> None:
    """
    Ensure systemd --user can run for a target account when this script is root.
    """
    u = get_user(username)
    if os.geteuid() != 0:
        return
    run(["loginctl", "enable-linger", username], check=False)
    run(["systemctl", "start", f"user@{u.pw_uid}.service"], check=False)

def chown_tree(path: Path, username: str) -> None:
    u = get_user(username)
    for base, dirs, fnames in os.walk(path):
        os.chown(base, u.pw_uid, u.pw_gid)
        for d in dirs:
            os.chown(os.path.join(base, d), u.pw_uid, u.pw_gid)
        for f in fnames:
            try:
                os.chown(os.path.join(base, f), u.pw_uid, u.pw_gid)
            except FileNotFoundError:
                pass

def home_path(username: str) -> Path:
    return Path(get_user(username).pw_dir)

def docker_socket(username: str) -> Path:
    return Path(f"/run/user/{get_user(username).pw_uid}/docker.sock")

def docker_cmd(username: str) -> list[str]:
    sock = docker_socket(username)
    return ["env", f"DOCKER_HOST=unix://{sock}", "docker"]

def normalize_url(host: str, default_scheme: str = "https") -> str:
    host = host.rstrip("/")
    if "://" not in host:
        host = f"{default_scheme}://{host}"
    return host

def secure_prompt(prompt: str) -> str:
    return getpass.getpass(prompt)

def request_json(
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    json_body=None,
    form=None,
    files=None,
    verify: bool = True,
    timeout: int = 20,
):
    try:
        import requests
    except ImportError:
        die("Python package 'requests' is required. Install it with: sudo apt install python3-requests")
    resp = requests.request(
        method,
        url,
        headers=headers,
        json=json_body,
        data=form,
        files=files,
        verify=verify,
        timeout=timeout,
    )
    if not resp.ok:
        detail = resp.text.strip()
        die(f"{method} {url} failed with HTTP {resp.status_code}: {detail}")
    if not resp.content:
        return None
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        return resp.json()
    try:
        return resp.json()
    except Exception:
        return resp.text

def portainer_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}

def rancher_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def default_agent_address(port: int) -> str:
    return f"{socket.getfqdn()}:{port}"

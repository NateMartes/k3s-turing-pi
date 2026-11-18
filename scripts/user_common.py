#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pwd
import queue
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Optional

from config_env import SYSADMIN_ENV, load_sysadmin_env_or_exit
from password_setup import MIN_PASSWORD_LENGTH, SYMBOLS, WORDS


load_sysadmin_env_or_exit()

STATE_ROOT = Path(__file__).resolve().parent / "state"
DEFAULT_RANCHER_HOST = os.getenv("RANCHER_HOSTNAME")
DEFAULT_PORTAINER_HOST = os.getenv("PORTAINER_HOSTNAME")
DEFAULT_HARBOR_HOST = os.getenv("HARBOR_HOSTNAME")
DEFAULT_ARGO_HOST = os.getenv("ARGO_HOSTNAME")
DEFAULT_PORTAINER_API_KEY = os.getenv("PORTAINER_API_KEY")
DEFAULT_RANCHER_API_KEY = os.getenv("RANCHER_TOKEN")
DEFAULT_HARBOR_ADMIN_PASSWORD = os.getenv("HARBOR_ADMIN_PASSWORD")

SELECTABLE_SERVICES = (
    "harbor",
    "rancher",
    "portainer",
    "portainer-agent",
    "docker-rootless",
    "argo-workflow-runner",
    "k3s-namespace",
)

SELECTABLE_SERVICE_DEPENDENCIES = {
    "harbor": (),
    "rancher": ("k3s-namespace",),
    "portainer": (),
    "portainer-agent": ("docker-rootless",),
    "docker-rootless": (),
    "argo-workflow-runner": ("k3s-namespace",),
    "k3s-namespace": (),
}

def parse_services(value: str) -> frozenset[str]:
    services = [service.strip() for service in value.split(",")]
    if not all(services):
        raise argparse.ArgumentTypeError(
            "only must be a comma-separated list without empty entries"
        )

    unknown = sorted(set(services) - set(SELECTABLE_SERVICES))
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown service(s): {', '.join(unknown)}; choose from: "
            f"{', '.join(SELECTABLE_SERVICES)}"
        )
    return frozenset(services)


def die(message: str, code: int = 1):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def require_hostname(value: Optional[str], variable: str, option: str) -> str:
    if value:
        return value
    die(
        f"{variable} is not set in {SYSADMIN_ENV}; provide {option} or update the file."
    )


def print_unverified_https_notice(services: list[tuple[str, str]]) -> None:
    endpoints = []
    for service, host in services:
        endpoint = host.rstrip("/")
        if "://" not in endpoint:
            endpoint = f"https://{endpoint}"
        if endpoint.lower().startswith("https://"):
            endpoints.append(f"{service} ({endpoint})")
    if endpoints:
        print(
            "WARNING: TLS certificate verification is disabled for: "
            + ", ".join(endpoints)
        )


def require_root():
    if os.geteuid() != 0:
        die("This command manages system accounts and must be run with sudo/root.")


def current_username() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def validate_username(username: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        die(
            "Username must start with a lowercase letter or underscore and contain "
            "only lowercase letters, digits, '_' or '-' (max 32 characters)."
        )
    return username


def generate_password() -> str:
    # Exactly: <CapitalizedWord><symbol><digit><CapitalizedWord>, using secrets.
    while True:
        password = (
            f"{secrets.choice(WORDS)}"
            f"{secrets.choice(SYMBOLS)}"
            f"{secrets.choice(string.digits)}"
            f"{secrets.choice(WORDS)}"
        )
        if len(password) >= MIN_PASSWORD_LENGTH:
            return password


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        die(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if not any(character.isupper() for character in password):
        die("Password must contain at least one uppercase letter.")
    return password


def parse_quota(value: str) -> tuple[int, str]:
    """
    Return quota in KiB and normalized display form.
    Accepts e.g. 500MB, 5GB (binary MiB/GiB sizes for filesystem quota math).
    """
    m = re.fullmatch(r"\s*(\d+)\s*(MB|GB)\s*", value, flags=re.I)
    if not m:
        die("Quota must look like 500MB, 5GB, etc.")
    amount = int(m.group(1))
    unit = m.group(2).upper()
    if amount <= 0:
        die("Quota must be greater than zero.")
    kib = amount * (1024 if unit == "MB" else 1024 * 1024)
    return kib, f"{amount}{unit}"


def run(cmd: list[str], *, check=True, capture=False, env=None, input_data=None):
    kwargs = dict(check=check, text=True, env=env, input=input_data)
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return subprocess.run(cmd, **kwargs)


def _finish_status_line(label: str, success: bool):
    symbol = "✓" if success else "✗"
    print(f"{symbol} {label}")


def _render_live_log_window(label: str, frame: str, lines, rendered: bool):
    if rendered:
        print("\033[5A", end="")
    rows = [f"{frame} {label}"] + [f"│ {line}" for line in lines]
    rows.extend(["│"] * (5 - len(rows)))
    for row in rows:
        print(f"\r\033[2K{row}")


def _finish_live_log_window(label: str, success: bool, rendered: bool):
    if not rendered:
        _finish_status_line(label, success)
        return
    symbol = "✓" if success else "✗"
    print("\033[5A", end="")
    rows = [f"{symbol} {label}", "", "", "", ""]
    for row in rows:
        print(f"\r\033[2K{row}")
    # Leave the cursor immediately below the completed status line.
    print("\033[4A", end="", flush=True)


def _print_log_group(label: str, output: str):
    print(f"┌─ {label} logs")
    if output.strip():
        for line in output.rstrip().splitlines():
            print(f"│ {line}")
    else:
        print("│ (no command output)")
    print("└─")


def run_with_loading(
    cmd: list[str],
    *,
    label: str,
    raw_logs: bool = False,
    check: bool = True,
    env=None,
):
    """Run a command with a compact spinner, showing grouped output on failure."""
    if raw_logs:
        print(f"==> {label}")
        return run(cmd, check=check, env=env)

    process = subprocess.Popen(
        cmd,
        text=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    interactive = sys.stdout.isatty()
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    frame = 0
    output_lines = []
    recent_lines = deque(maxlen=4)
    messages = queue.Queue()
    rendered = False

    def read_output():
        for line in process.stdout:
            messages.put(line)
        messages.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    if not interactive:
        print(f"… {label}")

    try:
        finished_reading = False
        while True:
            try:
                message = messages.get(timeout=0.1)
                if message is None:
                    finished_reading = True
                else:
                    output_lines.append(message)
                    recent_lines.append(message.rstrip("\r\n"))
                while not finished_reading:
                    try:
                        message = messages.get_nowait()
                    except queue.Empty:
                        break
                    if message is None:
                        finished_reading = True
                    else:
                        output_lines.append(message)
                        recent_lines.append(message.rstrip("\r\n"))
            except queue.Empty:
                pass

            if interactive and not finished_reading:
                _render_live_log_window(
                    label,
                    frames[frame % len(frames)],
                    list(recent_lines),
                    rendered,
                )
                rendered = True
                frame += 1
            if finished_reading:
                break
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        if interactive and rendered:
            _finish_live_log_window(label, False, rendered)
        raise

    process.wait()
    reader.join()
    output = "".join(output_lines)
    completed = subprocess.CompletedProcess(cmd, process.returncode, output, None)
    success = process.returncode == 0
    if interactive:
        _finish_live_log_window(label, success, rendered)
    else:
        if success and recent_lines:
            for line in recent_lines:
                print(f"│ {line}")
        _finish_status_line(label, success)
    if not success:
        _print_log_group(label, output or "")
        if check:
            raise subprocess.CalledProcessError(
                process.returncode,
                cmd,
                output=output,
            )
    return completed


def plumbing_dir() -> Path:
    return Path(__file__).resolve().parent / "plumbing-scripts"


def run_plumbing(
    name: str,
    args: list[str],
    *,
    extra_env: Optional[dict[str, str]] = None,
    check=True,
    raw_logs: bool = False,
    label: Optional[str] = None,
):
    script = plumbing_dir() / name
    if not script.exists():
        die(f"Plumbing script not found: {script}")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return run_with_loading(
        [str(script), *args],
        label=label or name.replace("-", " ").capitalize(),
        raw_logs=raw_logs,
        check=check,
        env=env,
    )


def state_path(username: str) -> Path:
    return STATE_ROOT / f"{username}.json"


def load_state(username: str) -> dict:
    path = state_path(username)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        die(f"Could not read state file {path}: {exc}")


def save_state(username: str, state: dict):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_ROOT, 0o700)
    path = state_path(username)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def remove_state(username: str):
    state_path(username).unlink(missing_ok=True)


def home_for(username: str) -> Path:
    return Path(pwd.getpwnam(username).pw_dir)


def home_filesystem(home: Path) -> str:
    proc = run(["findmnt", "-no", "TARGET", "-T", str(home)], capture=True)
    target = proc.stdout.strip()
    if not target:
        die(f"Could not determine filesystem containing {home}.")
    return target


def set_quota(username: str, quota_text: str) -> dict:
    if not shutil.which("setquota"):
        die("setquota was not found. Install the 'quota' package first.")

    kib, normalized = parse_quota(quota_text)
    home = home_for(username)
    mount = home_filesystem(home)

    # setquota uses block limits in KiB on Linux quota-tools.
    proc = run(
        ["setquota", "-u", username, str(kib), str(kib), "0", "0", mount],
        check=False,
        capture=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        die(
            f"Could not set quota on {mount}: {detail}\n"
            "Make sure user quotas are enabled on the filesystem (usrquota)."
        )

    return {"quota": normalized, "quota_kib": kib, "quota_filesystem": mount}


def choose_agent_port(start: int = 9001, stop: int = 9999) -> int:
    for port in range(start, stop + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            return port
        except OSError:
            pass
        finally:
            s.close()
    die(f"No free TCP port was found between {start} and {stop}.")


def agent_address(port: int) -> str:
    return f"{socket.getfqdn()}:{port}"


def _https_url(host: Optional[str]) -> str:
    if not host:
        return "(not configured)"
    endpoint = host.rstrip("/")
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    return endpoint


def _print_credential_group(name: str, fields: list[tuple[str, object]]) -> None:
    print(f"\n{name}")
    print("-" * len(name))
    width = max(len(label) for label, _ in fields) + 1
    for label, value in fields:
        print(f"{label + ':':<{width}} {value}")


def print_resource_summary(
    state: dict,
    *,
    include_password: Optional[str] = None,
    include_k3s_token: Optional[str] = None,
    include_linux_password: bool = True,
):
    username = state.get("username", "?")
    print("\nCreated/managed resources")
    print("-------------------------")
    linux_user = username
    if state.get("linux_user_created") is False:
        linux_user += " (pre-existing)"
    print(f"Linux user:           {linux_user}")
    print(f"Home directory:       {state.get('home', '?')}")
    if state.get("filesystem_quota") is False:
        print("Quota:                disabled")
    else:
        print(
            f"Quota:                {state.get('quota', '?')} on "
            f"{state.get('quota_filesystem', '?')}"
        )
    if state.get("services"):
        print(f"Selected services:    {', '.join(state['services'])}")
    elif state.get("excluded"):
        # Backward compatibility for state created by the earlier --exclude API.
        selected = sorted(set(SELECTABLE_SERVICES) - set(state["excluded"]))
        print(f"Selected services:    {', '.join(selected)}")
    print(f"Docker rootless:      {state.get('docker_rootless', False)}")
    print(f"Portainer agent:      {state.get('portainer_agent', False)}")
    if state.get("portainer_agent"):
        print(f"Agent address:        {state.get('agent_address', '?')}")
    if state.get("k3s_namespace"):
        print(f"K3s namespace:        {state.get('namespace', '?')}")
        if state.get("k3s_quota") is False:
            print("K3s quota:            disabled")
        else:
            print(
                "K3s quota:            "
                f"CPU {state.get('k3s_cpu_quota', '?')}, "
                f"memory {state.get('k3s_memory_quota', '?')}, "
                f"storage {state.get('k3s_storage_quota', '?')}, "
                f"GPUs {state.get('k3s_gpu_quota', '?')}"
            )
    else:
        print("K3s namespace:        False")
    print(f"Argo workflow runner: {state.get('argo_workflow_runner', False)}")
    if state.get("rancher_account"):
        print(f"Rancher account:      {state.get('rancher_user', '?')}")
        print(f"Rancher project:      {state.get('rancher_project', '?')}")
    else:
        print("Rancher account:      False")
    if state.get("harbor_account"):
        print(f"Harbor account:       {state.get('harbor_user', '?')}")
        print(f"Harbor project:       {state.get('harbor_project', '?')}")
        if state.get("harbor_quota") is False:
            print("Harbor quota:         disabled")
        else:
            print(
                f"Harbor quota:         "
                f"{state.get('harbor_storage_quota', '10GB')}"
            )
    else:
        print("Harbor account:       False")
    if state.get("portainer_account"):
        print(f"Portainer account:    {state.get('portainer_user', '?')}")
        print(
            "Portainer environment: "
            f"{state.get('portainer_environment', '?')}"
        )
    else:
        print("Portainer account:    False")
    if include_password is None and include_k3s_token is None:
        return

    print("\nLogin credentials (sensitive)")
    print("-----------------------------")

    if include_password is not None:
        linux_group = (
            "Linux / rootless Docker"
            if state.get("docker_rootless")
            else "Linux"
        )
        _print_credential_group(
            linux_group,
            [
                ("Username", username),
                (
                    "Password",
                    include_password
                    if include_linux_password
                    else "unchanged (pre-existing account)",
                ),
                ("Home", state.get("home", "?")),
            ],
        )

    if include_k3s_token is not None and state.get("k3s_namespace"):
        home = state.get("home")
        kubeconfig = f"{home}/.kube/config" if home else "?"
        _print_credential_group(
            "K3s / kubectl",
            [
                ("Service account", state.get("k3s_service_account", f"{username}-user")),
                ("Namespace", state.get("namespace", "?")),
                ("Kubeconfig", kubeconfig),
                ("Token", include_k3s_token),
            ],
        )
        if state.get("argo_workflow_runner"):
            _print_credential_group(
                "Argo Workflows",
                [
                    ("URL", _https_url(state.get("argo_host"))),
                    ("Authorization", f"Bearer {include_k3s_token}"),
                ],
            )

    if include_password is not None and state.get("harbor_account"):
        _print_credential_group(
            "Harbor",
            [
                ("URL", _https_url(state.get("harbor_host"))),
                ("Username", state.get("harbor_user", username)),
                ("Password", include_password),
                ("Project", state.get("harbor_project", "?")),
            ],
        )
    if include_password is not None and state.get("rancher_account"):
        _print_credential_group(
            "Rancher",
            [
                ("URL", _https_url(state.get("rancher_host"))),
                ("Username", state.get("rancher_user", username)),
                ("Password", include_password),
                ("Project", state.get("rancher_project", "?")),
            ],
        )
    if include_password is not None and state.get("portainer_account"):
        _print_credential_group(
            "Portainer",
            [
                ("URL", _https_url(state.get("portainer_host"))),
                ("Username", state.get("portainer_user", username)),
                ("Password", include_password),
                ("Environment", state.get("portainer_environment", "?")),
            ],
        )

    if include_k3s_token is not None:
        print(
            "\nStore and share this output securely. The password is not saved by "
            "these scripts, and the token grants the user's Kubernetes permissions."
        )
    else:
        print(
            "\nStore and share this output securely. The password is not saved by "
            "these scripts."
        )

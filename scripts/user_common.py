#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pwd
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
from pathlib import Path
from typing import Optional

STATE_ROOT = Path(__file__).resolve().parent / "state"
DEFAULT_RANCHER_HOST = "rancher.192.168.1.102.sslip.io"
DEFAULT_PORTAINER_HOST = "portainer.192.168.1.102.sslip.io"
DEFAULT_PORTAINER_API_KEY = "changeme"
DEFAULT_RANCHER_API_KEY = "changeme"

WORDS = (
    "acacia almond alpine anchor autumn bamboo beacon birchwood blossom bronze "
    "canyon cedarwood cherry circle citrus cobalt cometary copper crystal desert "
    "dragon emerald falcon forest galaxy garden glacier golden harbor hazelnut "
    "island ivorywood jasmine juniper lantern lavender marble meadow meteor mosaic "
    "nectar oceanic orchid pebble planet quartz rabbit rocket silver spruce summit "
    "sunrise thunder timber valley velvet violet willow winter zenith"
).split()
SYMBOLS = "!@#$%&*+-_=?"

def die(message: str, code: int = 1):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


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
    # Exactly: <word><symbol><word>, using the secrets module.
    return f"{secrets.choice(WORDS)}{secrets.choice(SYMBOLS)}{secrets.choice(WORDS)}"


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


def plumbing_dir() -> Path:
    return Path(__file__).resolve().parent / "plumbing-scripts"


def run_plumbing(name: str, args: list[str], *, extra_env: Optional[dict[str, str]] = None, check=True):
    script = plumbing_dir() / name
    if not script.exists():
        die(f"Plumbing script not found: {script}")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return run([str(script), *args], check=check, env=env)


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


def print_resource_summary(state: dict, *, include_password: Optional[str] = None):
    username = state.get("username", "?")
    print("\nCreated/managed resources")
    print("-------------------------")
    print(f"Linux user:           {username}")
    print(f"Home directory:       {state.get('home', '?')}")
    print(f"Quota:                {state.get('quota', '?')} on {state.get('quota_filesystem', '?')}")
    print(f"Docker rootless:      {state.get('docker_rootless', False)}")
    print(f"Portainer agent:      {state.get('portainer_agent', False)}")
    if state.get("portainer_agent"):
        print(f"Agent address:        {state.get('agent_address', '?')}")
    print(f"K3s namespace:        {state.get('namespace', '?')}")
    print(f"Rancher account:      {state.get('rancher_user', '?')}")
    print(f"Rancher project:      {state.get('rancher_project', '?')}")
    print(f"Portainer account:    {state.get('portainer_user', '?')}")
    print(f"Portainer environment:{' ' if state.get('portainer_environment') else ''}{state.get('portainer_environment', '?')}")
    if include_password is not None:
        print(f"\nGenerated password:   {include_password}")
        print("Store this securely; it is not saved by these scripts.")

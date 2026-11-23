from __future__ import annotations

import getpass
import ipaddress
import os
import pwd
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANSIBLE_DIR = PROJECT_ROOT / "ansible"
INVENTORY_PATH = ANSIBLE_DIR / "inventory.yml"
GROUP_VARS_PATH = ANSIBLE_DIR / "group_vars" / "all.yml"
ENV_PATH = Path(os.environ.get("JIHWIJA_ENV_FILE", PROJECT_ROOT / "etc" / "jihwija.env"))
SERVICES_DIR = PROJECT_ROOT / "jihwija-services"
PLUMBING_DIR = Path(__file__).resolve().parents[1]


class JihwijaError(RuntimeError):
    pass


def run_plumbing(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run another public plumbing operation without going through the CLI."""
    script = PLUMBING_DIR / name
    if not script.is_file() or not os.access(script, os.X_OK):
        raise JihwijaError(f"Plumbing script is missing or not executable: {script}")
    return subprocess.run([str(script), *args], check=True, text=True)


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=os.sys.stderr)
    raise SystemExit(code)


def require_root() -> None:
    if os.geteuid() != 0:
        die("This operation must be run with sudo or as root.")


def prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input(f"{label}{suffix}: ").strip()
    return value if value else (default or "")


def prompt_bool(label: str, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    value = input(f"{label} [{marker}] ").strip().lower()
    if not value:
        return default
    if value in {"y", "yes"}:
        return True
    if value in {"n", "no"}:
        return False
    die("Expected yes or no.", 2)


def load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise JihwijaError(f"File not found: {path}")
    except (OSError, yaml.YAMLError) as exc:
        raise JihwijaError(f"Could not read YAML from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise JihwijaError(f"Expected a YAML mapping in {path}.")
    return data


def timestamped_backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.{stamp}.{counter}.bak")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_yaml(path: Path, data: dict, *, backup: bool = True) -> Path | None:
    saved = timestamped_backup(path) if backup else None
    atomic_write(path, yaml.safe_dump(data, sort_keys=False), 0o644)
    return saved


def inventory_all(inventory: dict) -> dict:
    all_group = inventory.setdefault("all", {})
    if not isinstance(all_group, dict):
        raise JihwijaError("Inventory 'all' group must be a mapping.")
    return all_group


def iter_groups(group: dict, name: str = "all") -> Iterator[tuple[str, dict]]:
    yield name, group
    children = group.get("children", {}) or {}
    if not isinstance(children, dict):
        raise JihwijaError(f"Group {name!r} children must be a mapping.")
    for child_name, child in children.items():
        if not isinstance(child, dict):
            raise JihwijaError(f"Group {child_name!r} must be a mapping.")
        yield from iter_groups(child, child_name)


def inventory_groups(inventory: dict) -> dict[str, dict]:
    return dict(iter_groups(inventory_all(inventory)))


def inventory_hosts(inventory: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for _, group in iter_groups(inventory_all(inventory)):
        hosts = group.get("hosts", {}) or {}
        if not isinstance(hosts, dict):
            raise JihwijaError("Inventory hosts entries must be mappings.")
        for hostname, variables in hosts.items():
            variables = variables or {}
            if not isinstance(variables, dict):
                raise JihwijaError(f"Variables for {hostname!r} must be a mapping.")
            if hostname in result and result[hostname] != variables:
                raise JihwijaError(f"Host {hostname!r} has conflicting definitions.")
            result[hostname] = variables
    return result


def group_for_host(inventory: dict, hostname: str) -> str | None:
    for name, group in iter_groups(inventory_all(inventory)):
        if hostname in (group.get("hosts", {}) or {}):
            return name
    return None


def add_host(inventory: dict, group_name: str, hostname: str, variables: dict) -> None:
    groups = inventory_groups(inventory)
    if group_name == "all":
        group = inventory_all(inventory)
    elif group_name in groups:
        group = groups[group_name]
    else:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", group_name):
            raise JihwijaError(f"Invalid inventory group name: {group_name!r}")
        group = inventory_all(inventory).setdefault("children", {}).setdefault(
            group_name, {}
        )
    group.setdefault("hosts", {})[hostname] = variables


def remove_host(inventory: dict, hostname: str) -> bool:
    removed = False
    for _, group in iter_groups(inventory_all(inventory)):
        hosts = group.get("hosts", {}) or {}
        if hostname in hosts:
            del hosts[hostname]
            removed = True
    return removed


def validate_networks(settings: dict, hosts: dict[str, dict]) -> None:
    try:
        lan = ipaddress.ip_network(settings["k3s_lan_cidr"], strict=False)
        pods = ipaddress.ip_network(settings["k3s_cluster_cidr"], strict=False)
        services = ipaddress.ip_network(settings["k3s_service_cidr"], strict=False)
    except (KeyError, ValueError) as exc:
        raise JihwijaError(f"Invalid cluster network: {exc}") from exc
    if lan.version != 4 or pods.version != 4 or services.version != 4:
        raise JihwijaError("Jihwija currently requires IPv4 cluster networks.")
    if lan.overlaps(pods) or lan.overlaps(services) or pods.overlaps(services):
        raise JihwijaError("LAN, Pod, and Service networks must not overlap.")
    seen: dict[str, str] = {}
    for hostname, variables in hosts.items():
        address = variables.get("ansible_host")
        if not address:
            raise JihwijaError(f"Host {hostname!r} has no ansible_host.")
        try:
            ip = ipaddress.ip_address(str(address))
        except ValueError as exc:
            raise JihwijaError(
                f"Host {hostname!r} ansible_host must be an IP address: {address!r}"
            ) from exc
        if ip not in lan:
            raise JihwijaError(f"Host {hostname!r} address {ip} is outside {lan}.")
        if str(ip) in seen:
            raise JihwijaError(
                f"Hosts {seen[str(ip)]!r} and {hostname!r} share address {ip}."
            )
        seen[str(ip)] = hostname


def operator_command(command: list[str]) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    username = env.get("SUDO_USER") if os.geteuid() == 0 else None
    if not username or username == "root":
        return command, env
    try:
        account = pwd.getpwnam(username)
    except KeyError:
        raise JihwijaError(f"Invoking user does not exist: {username}")
    env.update(HOME=account.pw_dir, USER=username, LOGNAME=username)
    return ["runuser", "-u", username, "--", *command], env


def run_ansible_playbook(playbook: str, extra_args: list[str] | None = None) -> None:
    command = [
        "ansible-playbook",
        "-i",
        str(INVENTORY_PATH),
        str(ANSIBLE_DIR / playbook),
        *(extra_args or []),
    ]
    command, env = operator_command(command)
    subprocess.run(command, check=True, env=env)


def preflight_host(address: str, user: str, *, require_amd64: bool = False) -> str:
    setup = [
        "ansible", "all", "-i", f"{address},", "-u", user,
        "-m", "setup", "-a", "filter=ansible_distribution,ansible_architecture",
    ]
    setup, env = operator_command(setup)
    result = subprocess.run(setup, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        raise JihwijaError(f"SSH/fact preflight failed for {address}:\n{result.stderr or result.stdout}")
    if '"ansible_distribution": "Ubuntu"' not in result.stdout:
        raise JihwijaError(f"Node {address} must run Ubuntu.")
    architecture = "amd64" if any(value in result.stdout for value in ('"x86_64"', '"amd64"')) else "other"
    if require_amd64 and architecture != "amd64":
        raise JihwijaError(f"Jihwija service node {address} must use AMD64 for Harbor.")

    become = [
        "ansible", "all", "-i", f"{address},", "-u", user,
        "-b", "-m", "command", "-a", "true",
    ]
    become, env = operator_command(become)
    result = subprocess.run(become, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        raise JihwijaError(f"Remote sudo preflight failed for {address}:\n{result.stderr or result.stdout}")
    return architecture


def kubectl_command() -> list[str]:
    if shutil.which("k3s"):
        return ["k3s", "kubectl"]
    if shutil.which("kubectl"):
        return ["kubectl"]
    raise JihwijaError("Neither k3s nor kubectl was found in PATH.")


def kubectl(*args: str, capture: bool = False, check: bool = True):
    return subprocess.run(
        [*kubectl_command(), *args],
        check=check,
        text=True,
        capture_output=capture,
    )


def parse_env(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = shlex.split(stripped, comments=True)
        if fields and fields[0] == "export":
            fields = fields[1:]
        if len(fields) != 1 or "=" not in fields[0]:
            raise JihwijaError(f"{path}:{number}: expected NAME=value")
        name, value = fields[0].split("=", 1)
        values[name] = value
    return values


def write_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    lines = [f"export {key}={shlex.quote(value)}" for key, value in sorted(values.items())]
    timestamped_backup(path)
    atomic_write(path, "\n".join(lines) + "\n", 0o600)


def validate_hostname(value: str) -> str:
    label = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
    if (
        len(value) > 253
        or "://" in value
        or "/" in value
        or not value
        or any(not label.fullmatch(part) for part in value.split("."))
    ):
        raise JihwijaError("Expected a DNS hostname without a scheme, port, or path.")
    return value


def secure_value(label: str) -> str:
    value = getpass.getpass(f"{label}: ")
    if not value:
        raise JihwijaError("Value must not be empty.")
    return value


BAK_ASCII = r"""                    =*=     ****   ###                      
                    =******=******######  *##               
              *******=*****=***==*###*#*######              
          =**********==***==****=###**=####*#######         
        *******==*****==***==**==###**####***#######        
       *********==****==***==**=*##**####**#####**##= **    
   *******===*****==***==**==**=###**##**####***********=   
   *********====****==**==**=**=##=*##**###*********===*=   
  =***===******===***==**==*=*=*#**#**###*******====**######
=********====*****===**==*=*===##*#**##*=***===**###########
=*************===****==*==*====#*#*#**==****########*****## 
         **************=======*********######******         
                  ****====== ***##*#*******                 
                   =#######==#######=####                   
                  ###   =##===#===##=   ##                  
                   #####=##=#####=########                  
                    ###### =#==##= #####                    
                             ||.                            
                            .||.                            
                            .||.                            
                            .||.                            
                            .||.                            

                          Jihwija"""
JIHWIJA_ASCII = BAK_ASCII


def print_bak() -> None:
    print(BAK_ASCII)


def print_jihwija() -> None:
    print(BAK_ASCII)


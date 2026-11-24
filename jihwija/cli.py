from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator


ROUTES = {
    "init": "init-cluster.py",
    "install": {
        "k3s": "install-k3s.py",
    },
    "uninstall": {
        "k3s": "uninstall-k3s.py",
    },
    "enable": {
        "quotas": "enable-quotas.py",
    },
    "disable": {
        "quotas": "disable-quotas.py",
    },
    "set": {
        "secret": "set-secret.py",
        "hostname": "set-hostname.py",
        "user": {
            "quota": "change-user-quota.py",
            "password": "change-user-password.py",
        },
    },
    "deploy": "deploy-services.py",
    "add": {
        "node": "add-node.py",
        "user": "create-user.py",
    },
    "remove": {
        "node": "remove-node.py",
        "user": "remove-user.py",
    },
    "grant": {
        "user": "grant-user-privilege.py",
    },
    "revoke": {
        "user": "revoke-user-privilege.py",
    },
    "trust": {
        "certs": "trust-k3s-certs.py",
    },
}

COMMAND_DESCRIPTIONS: list[tuple[str, str]] = [
    ("init INVENTORY", "initialize cluster inventory and settings"),
    ("install k3s", "install or reconcile K3s"),
    ("uninstall k3s", "remove K3s from every inventory node"),
    ("enable quotas PATH", "enable filesystem user quotas"),
    ("disable quotas PATH", "disable filesystem user quotas"),
    ("set secret KEY", "store a protected service secret"),
    ("set hostname SERVICE", "configure a service hostname"),
    ("set user quota [USER]", "update a managed user's quotas"),
    ("set user password [USER]", "update a managed user's passwords"),
    ("deploy", "deploy all Jihwija services"),
    ("add node HOSTNAME IP", "add and provision a worker node"),
    ("remove node HOSTNAME", "drain and remove a worker node"),
    ("add user [USERNAME]", "provision a managed user"),
    ("remove user [USERNAME]", "remove a managed user"),
    ("grant user USERNAME PRIVILEGE", "grant an allowlisted user privilege"),
    ("revoke user USERNAME PRIVILEGE", "revoke an allowlisted user privilege"),
    ("trust certs", "install and distribute service certificate trust"),
]
COMMAND_WIDTH = max(len(syntax) for syntax, _ in COMMAND_DESCRIPTIONS) + 2


def format_help(prefix: str = "") -> str:
    """Format help text for the top-level CLI or an intermediate command group."""
    if not prefix:
        lines = [
            "usage: jihwija COMMAND [ARGS]",
            "",
            "Conduct a native K3s and Ansible cluster.",
            "",
            "commands:",
        ]
        for syntax, desc in COMMAND_DESCRIPTIONS:
            lines.append(f"  {syntax:<{COMMAND_WIDTH}} {desc}")
        lines.append("")
        lines.append("Run `jihwija COMMAND --help` for command-specific options.")
        return "\n".join(lines) + "\n"

    prefix_space = prefix + " "
    matched = []
    for syntax, desc in COMMAND_DESCRIPTIONS:
        if syntax.startswith(prefix_space):
            matched.append((syntax[len(prefix_space):], desc))

    if not matched:
        return ""

    lines = [
        f"usage: jihwija {prefix} COMMAND [ARGS]",
        "",
        "commands:",
    ]
    for syntax, desc in matched:
        lines.append(f"  {syntax:<{COMMAND_WIDTH}} {desc}")
    lines.append("")
    lines.append(f"Run `jihwija {prefix} COMMAND --help` for command-specific options.")
    return "\n".join(lines) + "\n"


HELP = format_help()


def project_root() -> Path:
    configured = os.environ.get("JIHWIJA_ROOT")
    if configured:
        return Path(configured)
    source_root = Path(__file__).resolve().parent.parent
    if (source_root / "scripts" / "plumbing-scripts").is_dir():
        return source_root
    return Path("/opt/jihwija")


def resolve_route(args: list[str]) -> tuple[str, int] | None:
    """Resolve command words to a plumbing script and consumed argument count."""
    target: object = ROUTES
    consumed = 0
    while isinstance(target, dict) and consumed < len(args):
        target = target.get(args[consumed])
        if target is None:
            return None
        consumed += 1
    if isinstance(target, str):
        return target, consumed
    return None


def traverse_route(args: list[str]) -> tuple[object, int]:
    """Traverse ROUTES as far as possible with the provided words."""
    target: object = ROUTES
    consumed = 0
    while isinstance(target, dict) and consumed < len(args):
        word = args[consumed]
        if word not in target:
            break
        target = target[word]
        consumed += 1
    return target, consumed


def route_scripts(routes: dict[str, object] = ROUTES) -> Iterator[str]:
    """Yield every plumbing script registered anywhere in the command tree."""
    for target in routes.values():
        if isinstance(target, str):
            yield target
        elif isinstance(target, dict):
            yield from route_scripts(target)
        else:
            raise TypeError(f"Invalid route target: {target!r}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args in (["-h"], ["--help"], ["help"]):
        print(HELP, end="")
        return

    if args in (["-v"], ["--version"]):
        print("jihwija 0.1.0")
        return

    # Normalize `jihwija help ...` to equivalent `--help` invocation.
    if args[0] == "help" and len(args) > 1:
        args = [*args[1:], "--help"]

    resolved = resolve_route(args)
    if resolved is None:
        target, consumed = traverse_route(args)
        remaining = args[consumed:]
        prefix = " ".join(args[:consumed])

        # If traversal reached a command group and user asked for help or provided no subcommand:
        if isinstance(target, dict) and (not remaining or remaining in (["-h"], ["--help"], ["help"])):
            group_help = format_help(prefix)
            if group_help:
                print(group_help, end="")
                return

        # Otherwise report an unknown command or subcommand.
        if prefix:
            unknown = f"{prefix} {remaining[0]}" if remaining else prefix
            print(f"jihwija: unknown command: {unknown}", file=sys.stderr)
            print(f"Run `jihwija {prefix} --help` for usage.", file=sys.stderr)
        else:
            unknown = " ".join(args[:2])
            print(f"jihwija: unknown command: {unknown}", file=sys.stderr)
            print("Run `jihwija --help` for usage.", file=sys.stderr)
        raise SystemExit(2)

    script_name, consumed = resolved
    script = project_root() / "scripts" / "plumbing-scripts" / script_name
    if not script.is_file():
        print(f"jihwija: plumbing script is missing: {script}", file=sys.stderr)
        raise SystemExit(1)

    # Ensure virtualenv bin directory is in PATH and VIRTUAL_ENV is set so child
    # processes find the expected Python environment and dependencies.
    venv_bin = str(Path(sys.executable).resolve().parent)
    current_path = os.environ.get("PATH", "")
    if venv_bin not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{venv_bin}{os.pathsep}{current_path}" if current_path else venv_bin
    os.environ.setdefault("VIRTUAL_ENV", str(Path(sys.executable).resolve().parent.parent))

    prog_name = f"jihwija {' '.join(args[:consumed])}"

    # If the plumbing script is Python, run it via sys.executable so:
    # 1. sys.executable runs the script directly (preventing virtualenv/system-python mismatch).
    # 2. sys.argv[0] is set to the unified CLI command (e.g. `jihwija add node`), so
    #    argparse help and error messages display the CLI command rather than plumbing filenames.
    # 3. The plumbing directory is importable so scripts can load their shared `lib` package.
    is_python = True
    try:
        with script.open("rb") as handle:
            first_line = handle.readline()
            if first_line.startswith(b"#!") and b"python" not in first_line:
                is_python = False
    except OSError:
        pass

    if is_python:
        runner = (
            "import os, sys; "
            "prog, path = sys.argv[1], sys.argv[2]; "
            "sys.path.insert(0, os.path.dirname(path)); "
            "sys.argv = [prog, *sys.argv[3:]]; "
            "code = compile(open(path, 'rb').read(), path, 'exec'); "
            "scope = {'__name__': '__main__', '__file__': path, "
            "'__package__': None, '__cached__': None}; "
            "exec(code, scope)"
        )
        os.execv(
            sys.executable,
            [
                sys.executable,
                "-c",
                runner,
                prog_name,
                str(script),
                *args[consumed:],
            ],
        )
    else:
        os.execv(str(script), [prog_name, *args[consumed:]])


if __name__ == "__main__":
    main()

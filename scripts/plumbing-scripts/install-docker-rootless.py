#!/usr/bin/env python3

import argparse
import os
import platform
import shutil
import tempfile
from pathlib import Path

from lib.platform_common import (
    die,
    docker_socket,
    ensure_rootless_docker_apparmor,
    get_marker,
    get_user,
    home_path,
    info,
    require_root,
    run,
    run_as_target_user,
    determine_username
)


SUBID_COUNT = 65536
MARKER = get_marker("Docker Rootless")
COMPOSE_MANAGED_MARKER = ".docker-compose-managed-by-jihwija"


def compose_architecture() -> str:
    machine = platform.machine().lower()
    architectures = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "armv7": "armv7",
        "armv7l": "armv7",
        "ppc64le": "ppc64le",
        "riscv64": "riscv64",
        "s390x": "s390x",
    }

    try:
        return architectures[machine]
    except KeyError:
        die(
            f"Docker Compose does not provide a supported binary for "
            f"architecture {machine!r}."
        )


def has_subid(path: str, username: str) -> bool:
    try:
        for line in Path(path).read_text().splitlines():
            parts = line.split(":")

            if len(parts) != 3:
                continue

            try:
                count = int(parts[2])
            except ValueError:
                continue

            if parts[0] == username and count >= SUBID_COUNT:
                return True

    except FileNotFoundError:
        pass

    return False


def next_subid_start() -> int:
    max_end = 99999

    for path in ("/etc/subuid", "/etc/subgid"):
        try:
            for line in Path(path).read_text().splitlines():
                parts = line.split(":")

                if len(parts) != 3:
                    continue

                try:
                    start = int(parts[1])
                    count = int(parts[2])
                except ValueError:
                    continue

                max_end = max(max_end, start + count - 1)

        except FileNotFoundError:
            pass

    return (
        (max_end + 1 + SUBID_COUNT - 1)
        // SUBID_COUNT
        * SUBID_COUNT
    )


def ensure_subids(username: str) -> None:
    need_uid = not has_subid("/etc/subuid", username)
    need_gid = not has_subid("/etc/subgid", username)

    if not need_uid and not need_gid:
        return

    start = next_subid_start()
    end = start + SUBID_COUNT - 1

    if need_uid:
        info(f"Adding subordinate UID range {start}-{end} for {username}")
        run([
            "usermod",
            f"--add-subuids={start}-{end}",
            username,
        ])

    if need_gid:
        info(f"Adding subordinate GID range {start}-{end} for {username}")
        run([
            "usermod",
            f"--add-subgids={start}-{end}",
            username,
        ])


def ensure_prereqs() -> None:
    info("Installing rootless Docker prerequisites")

    run(["apt-get", "update"])

    run([
        "apt-get",
        "install",
        "-y",
        "uidmap",
        "dbus-user-session",
        "curl",
        "slirp4netns",
        "fuse-overlayfs",
    ])


def ensure_user_runtime(username: str) -> None:
    """
    Make sure the target user has a running systemd user manager and
    /run/user/<uid> before we try to use systemctl --user.
    """

    user = get_user(username)
    runtime_dir = Path(f"/run/user/{user.pw_uid}")

    info(f"Enabling systemd lingering for {username}")
    run(
        ["loginctl", "enable-linger", username],
        check=False,
    )

    info(f"Starting systemd user manager for {username}")
    run(
        ["systemctl", "start", f"user@{user.pw_uid}.service"],
        check=False,
    )

    if not runtime_dir.exists():
        die(
            f"User runtime directory {runtime_dir} was not created. "
            f"Cannot configure rootless Docker for {username}."
        )


def find_setup_tool(username: str) -> Path | None:
    home = home_path(username)

    candidates = [
        Path("/usr/bin/dockerd-rootless-setuptool.sh"),
        home / "bin/dockerd-rootless-setuptool.sh",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def install_rootless_binaries(username: str) -> None:
    info(f"Installing rootless Docker binaries for {username}")

    with tempfile.NamedTemporaryFile(
        prefix="docker-rootless-",
        delete=False,
    ) as file:
        installer = Path(file.name)

    try:
        run([
            "curl",
            "-fsSL",
            "https://get.docker.com/rootless",
            "-o",
            str(installer),
        ])

        # NamedTemporaryFile defaults to permissions the target user
        # cannot necessarily read.
        installer.chmod(0o755)

        run_as_target_user(
            username,
            ["sh", str(installer)],
        )

    finally:
        installer.unlink(missing_ok=True)


def compose_is_available(username: str) -> bool:
    result = run_as_target_user(
        username,
        ["docker", "compose", "version"],
        check=False,
        capture=True,
    )
    return result.returncode == 0


def install_compose_plugin(username: str) -> None:
    if compose_is_available(username):
        info(f"Docker Compose is already available for {username}")
        return

    user = get_user(username)
    docker_config = home_path(username) / ".docker"
    plugin_dir = docker_config / "cli-plugins"
    plugin_path = plugin_dir / "docker-compose"
    marker_path = plugin_dir / COMPOSE_MANAGED_MARKER
    architecture = compose_architecture()
    download_url = (
        "https://github.com/docker/compose/releases/latest/download/"
        f"docker-compose-linux-{architecture}"
    )

    info(f"Installing Docker Compose plugin for {username}")

    with tempfile.NamedTemporaryFile(
        prefix="docker-compose-",
        delete=False,
    ) as file:
        installer = Path(file.name)

    try:
        run([
            "curl",
            "-fsSL",
            download_url,
            "-o",
            str(installer),
        ])

        docker_config.mkdir(mode=0o700, exist_ok=True)
        plugin_dir.mkdir(mode=0o700, exist_ok=True)
        shutil.copyfile(installer, plugin_path)
        plugin_path.chmod(0o755)
        marker_path.write_text(f"Installed from {download_url}\n")
        marker_path.chmod(0o600)

        for path in (docker_config, plugin_dir, plugin_path, marker_path):
            os.chown(path, user.pw_uid, user.pw_gid)
    finally:
        installer.unlink(missing_ok=True)

    if not compose_is_available(username):
        die(
            "Docker Compose was downloaded, but "
            f"'docker compose version' failed for {username}."
        )


def configure_rootless_docker(username: str) -> None:
    tool = find_setup_tool(username)

    if tool is None:
        install_rootless_binaries(username)
        tool = find_setup_tool(username)

    if tool is None:
        die(
            "dockerd-rootless-setuptool.sh was not found "
            "after installing rootless Docker."
        )

    info(f"Configuring rootless Docker for {username}")

    result = run_as_target_user(
        username,
        [str(tool), "install"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        output = (
            (result.stdout or "")
            + "\n"
            + (result.stderr or "")
        ).strip()

        # The setup tool may report that Docker is already installed.
        if "already" not in output.lower():
            if "apparmor" in output.lower():
                die(
                    f"{output}\n\n"
                    "Rootless Docker was blocked by AppArmor. Verify that "
                    "kernel.apparmor_restrict_unprivileged_userns is 0; "
                    "this installer manages that setting when the kernel exposes it."
                )
            die(output)


def enable_docker_service(username: str) -> None:
    info(f"Enabling rootless Docker service for {username}")

    result = run_as_target_user(
        username,
        [
            "systemctl",
            "--user",
            "enable",
            "--now",
            "docker.service",
        ],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        die(
            "Failed to enable the user's Docker service:\n"
            + (
                result.stderr
                or result.stdout
                or "unknown systemctl error"
            ).strip()
        )


def update_profile(username: str) -> None:
    user = get_user(username)
    home = home_path(username)
    shell_rc = home / ".profile"

    block = (
        f"\n{MARKER}\n"
        'export PATH="$HOME/bin:$PATH"\n'
        f'export DOCKER_HOST="unix:///run/user/{user.pw_uid}/docker.sock"\n'
    )

    text = shell_rc.read_text() if shell_rc.exists() else ""

    if MARKER in text:
        return

    shell_rc.write_text(text + block)

    os.chown(
        shell_rc,
        user.pw_uid,
        user.pw_gid,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Install Docker Engine in rootless mode "
            "for a Linux user."
        )
    )

    parser.add_argument(
        "-u",
        "--username",
        default=None,
        help="Linux user that should own the rootless Docker daemon.",
    )

    args = parser.parse_args()

    # This plumbing script itself always runs as root.
    require_root()

    username = determine_username(args.username)
    user = get_user(username)

    if username == "root" or user.pw_uid == 0:
        die("Rootless Docker cannot be installed for the root account.")

    ensure_prereqs()
    ensure_subids(username)
    ensure_rootless_docker_apparmor(username)

    # Do this before invoking Docker's rootless installer so the user's
    # XDG_RUNTIME_DIR and systemd user bus exist.
    ensure_user_runtime(username)

    configure_rootless_docker(username)
    install_compose_plugin(username)
    enable_docker_service(username)
    update_profile(username)

    print()
    print(f"Rootless Docker and Docker Compose configured for {username}.")
    print(f"Socket: {docker_socket(username)}")
    print(
        "The user should log out and back in, "
        "or run: source ~/.profile"
    )


if __name__ == "__main__":
    main()

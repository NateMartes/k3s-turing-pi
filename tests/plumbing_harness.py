from __future__ import annotations

import ast
import importlib
import os
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PLUMBING = ROOT / "scripts" / "plumbing-scripts"


SCRIPT_NAMES = (
    "add-node.py",
    "change-user-password.py",
    "change-user-quota.py",
    "create-user.py",
    "deploy-services.py",
    "disable-quotas.py",
    "enable-quotas.py",
    "grant-user-privilege.py",
    "init-cluster.py",
    "install-argo-workflow-runner.py",
    "install-docker-rootless.py",
    "install-harbor-account.py",
    "install-k3s-namespace.py",
    "install-k3s.py",
    "install-portainer-account.py",
    "install-portainer-agent.py",
    "install-rancher-account.py",
    "k3s-taint-gpu-nodes.py",
    "k3s-untaint-gpu-nodes.py",
    "remove-node.py",
    "remove-user.py",
    "revoke-user-privilege.py",
    "set-harbor-password.py",
    "set-harbor-quota.py",
    "set-hostname.py",
    "set-k3s-quota.py",
    "set-rancher-password.py",
    "set-secret.py",
    "trust-k3s-certs.py",
    "uninstall-argo-workflow-runner.py",
    "uninstall-docker-rootless.py",
    "uninstall-harbor-account.py",
    "uninstall-k3s-namespace.py",
    "uninstall-k3s.py",
    "uninstall-portainer-account.py",
    "uninstall-portainer-agent.py",
    "uninstall-rancher-account.py",
)


def script_path(script_name: str) -> Path:
    assert script_name in SCRIPT_NAMES
    return PLUMBING / script_name


def _has_main_guard(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.left, ast.Name) or test.left.id != "__name__":
            continue
        if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        value = test.comparators[0]
        if isinstance(value, ast.Constant) and value.value == "__main__":
            return True
    return False


def assert_script_contract(script_name: str) -> None:
    path = script_path(script_name)
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))

    assert path.suffix == ".py"
    assert os.access(path, os.X_OK)
    assert source.startswith("#!/usr/bin/env python3\n")
    assert any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "main"
        for node in tree.body
    )
    assert _has_main_guard(tree)


def assert_import_is_side_effect_free(
    script_name: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = script_path(script_name)
    monkeypatch.setenv(
        "JIHWIJA_ENV_FILE",
        str(tmp_path / "missing-jihwija.env"),
    )
    monkeypatch.syspath_prepend(str(PLUMBING))
    run_mock = Mock(side_effect=AssertionError("subprocess.run called during import"))
    popen_mock = Mock(side_effect=AssertionError("subprocess.Popen called during import"))

    module_name = f"_plumbing_test_{path.stem.replace('-', '_')}"
    with patch("subprocess.run", run_mock), patch("subprocess.Popen", popen_mock):
        namespace = runpy.run_path(str(path), run_name=module_name)

    assert callable(namespace["main"])
    run_mock.assert_not_called()
    popen_mock.assert_not_called()


def assert_help_is_safe(script_name: str, tmp_path: Path) -> None:
    path = script_path(script_name)
    env = os.environ.copy()
    env["JIHWIJA_ENV_FILE"] = str(tmp_path / "missing-jihwija.env")

    result = subprocess.run(
        [sys.executable, str(path), "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith("usage:")


def assert_mocked_dispatch(script_name: str, monkeypatch) -> None:
    path = script_path(script_name)
    monkeypatch.syspath_prepend(str(PLUMBING))
    jihwija_common = importlib.import_module("lib.jihwija_common")

    completed = subprocess.CompletedProcess([], 0)
    run_mock = Mock(return_value=completed)
    monkeypatch.setattr(jihwija_common.subprocess, "run", run_mock)

    result = jihwija_common.run_plumbing(script_name, "--probe")

    assert result is completed
    run_mock.assert_called_once_with(
        [str(path), "--probe"],
        check=True,
        text=True,
    )

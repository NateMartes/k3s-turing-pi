from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def _runtime_version() -> str:
    tree = ast.parse((ROOT / "jihwija" / "__init__.py").read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError("jihwija.__version__ is missing")


def test_release_versions_are_synchronized() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())

    assert project["project"]["version"] == _runtime_version() == manifest["."]


def test_current_version_has_a_changelog_entry() -> None:
    version = _runtime_version()
    changelog = (ROOT / "CHANGELOG.md").read_text()

    heading = (
        rf"^## \[{re.escape(version)}\]"
        rf"(?:\([^\n)]+\))?(?:\s|$)"
    )
    assert re.search(heading, changelog, flags=re.MULTILINE), (
        f"CHANGELOG.md has no entry for version {version}"
    )


def test_release_runs_container_integration_on_master() -> None:
    release = yaml.load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    integration = yaml.load(
        (
            ROOT
            / ".github"
            / "workflows"
            / "test-jihwija-in-containers.yml"
        ).read_text(),
        Loader=yaml.BaseLoader,
    )

    assert release["on"]["push"]["branches"] == ["master"]
    integration_job = release["jobs"]["container-integration"]
    assert integration_job["uses"] == (
        "./.github/workflows/test-jihwija-in-containers.yml"
    )
    assert "container-integration" in release["jobs"]["release"]["needs"]
    assert "workflow_call" in integration["on"]
    assert integration["jobs"]["test"]["steps"][-1]["run"] == (
        "tests/test-env/test-jihwija-with-containers.sh"
    )

from __future__ import annotations

import ast
import os

from tests.plumbing_harness import PLUMBING, SCRIPT_NAMES


def test_harness_manifest_covers_every_plumbing_command() -> None:
    actual = {
        path.name
        for path in PLUMBING.iterdir()
        if path.is_file() and os.access(path, os.X_OK)
    }
    assert actual == set(SCRIPT_NAMES)


def test_literal_internal_plumbing_targets_are_registered() -> None:
    registered = set(SCRIPT_NAMES)
    references = []

    for path in PLUMBING.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            function = node.func
            name = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr
                if isinstance(function, ast.Attribute)
                else None
            )
            target = node.args[0]
            if (
                name == "run_plumbing"
                and isinstance(target, ast.Constant)
                and isinstance(target.value, str)
            ):
                references.append((path, node.lineno, target.value))

    assert references
    missing = [reference for reference in references if reference[2] not in registered]
    assert missing == []

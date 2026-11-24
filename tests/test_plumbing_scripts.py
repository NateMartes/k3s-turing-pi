from __future__ import annotations

import pytest

from tests.plumbing_harness import (
    SCRIPT_NAMES,
    assert_help_is_safe,
    assert_import_is_side_effect_free,
    assert_mocked_dispatch,
    assert_script_contract,
)


@pytest.mark.parametrize("script_name", SCRIPT_NAMES)
def test_contract(script_name: str) -> None:
    assert_script_contract(script_name)


@pytest.mark.parametrize("script_name", SCRIPT_NAMES)
def test_import_is_side_effect_free(script_name: str, monkeypatch, tmp_path) -> None:
    assert_import_is_side_effect_free(script_name, monkeypatch, tmp_path)


@pytest.mark.parametrize("script_name", SCRIPT_NAMES)
def test_help_is_safe(script_name: str, tmp_path) -> None:
    assert_help_is_safe(script_name, tmp_path)


@pytest.mark.parametrize("script_name", SCRIPT_NAMES)
def test_dispatch_is_mocked(script_name: str, monkeypatch) -> None:
    assert_mocked_dispatch(script_name, monkeypatch)

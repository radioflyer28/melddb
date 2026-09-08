"""Every comparison implementation must satisfy the same executable workload."""
import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).parents[1] / "validation" / "comparison.py"
_spec = importlib.util.spec_from_file_location("comparison", _path)
comparison = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(comparison)


@pytest.mark.parametrize("implementation", comparison.IMPLEMENTATIONS)
@pytest.mark.parametrize("failure", [1, 2, 3, 4, "duplicate", "missing", "restrict", "caught_duplicate"])
def test_workload_equivalence(implementation, failure, tmp_path):
    comparison.verify_case(implementation, tmp_path, failure)


@pytest.mark.parametrize("implementation", comparison.IMPLEMENTATIONS)
def test_standalone_settings(implementation, tmp_path):
    assert comparison.SETTINGS[implementation](tmp_path / "settings.db") == {"theme": "dark"}

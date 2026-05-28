"""Run every recipe in ``scripts/api-examples/`` and assert it succeeds.

Each recipe is a Python file with a ``main(workdir: Path) -> None``
entry point. The test imports it, calls ``main`` with a fresh
``tmp_path``, and lets any exception surface — the recipe is the
documented public face of the API, so if it stops working the API
broke or the cookbook drifted.

Recipes are discovered automatically: drop a new ``recipe_name.py``
into the directory and this test will pick it up at the next run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_API_EXAMPLES_DIRPATH = _REPO_ROOT / "scripts" / "api-examples"


def _discover_recipes() -> list[Path]:
    if not _API_EXAMPLES_DIRPATH.is_dir():
        return []
    return sorted(p for p in _API_EXAMPLES_DIRPATH.glob("*.py") if not p.name.startswith("_"))


def _import_recipe(filepath: Path):
    """Import a recipe file as a module without polluting sys.modules globally."""
    spec = importlib.util.spec_from_file_location(f"_api_example_{filepath.stem}", filepath)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception:
        sys.modules.pop(spec.name, None)
        raise


@pytest.mark.parametrize(
    "recipe_filepath",
    _discover_recipes(),
    ids=lambda p: p.stem,
)
def test_recipe_runs_cleanly(
    recipe_filepath: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    module = _import_recipe(recipe_filepath)
    assert hasattr(module, "main"), (
        f"recipe {recipe_filepath.name} must expose a main(workdir) function"
    )
    module.main(tmp_path)
    # Recipes are allowed to print — capture so test output stays tidy.
    capsys.readouterr()

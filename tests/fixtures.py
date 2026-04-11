"""Shared test fixture helpers for the oaknut workspace.

This module lives at the workspace root so that every package's test
suite can reach the same set of reference disc images without
duplicating bytes across packages. Individual packages build their
own format-specific loader fixtures on top of the path exposed here.
"""

from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

REFERENCE_IMAGES_DIRPATH: Path = _WORKSPACE_ROOT / "tests" / "data" / "images"

"""Smoke tests asserting the oaknut-romfs package is wired into the workspace.

These are intentionally minimal — they prove the namespace package
imports and the version is in lockstep with the rest of the workspace.
The ROMFS format tests arrive with the implementation, driven by the
reference images under ``tests/data/images/romfs/``.
"""

from __future__ import annotations

import oaknut.romfs


def test_package_imports():
    assert oaknut.romfs is not None


def test_version_is_a_string():
    assert isinstance(oaknut.romfs.__version__, str)
    assert oaknut.romfs.__version__.count(".") == 2

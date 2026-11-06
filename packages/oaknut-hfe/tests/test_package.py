"""Smoke tests asserting the oaknut-hfe package is wired into the workspace."""

from __future__ import annotations

import oaknut.hfe


def test_package_imports():
    assert oaknut.hfe is not None


def test_version_is_a_string():
    assert isinstance(oaknut.hfe.__version__, str)
    assert oaknut.hfe.__version__.count(".") == 2

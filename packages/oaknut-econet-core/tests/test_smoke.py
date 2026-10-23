"""Smoke tests that the nested PEP 420 namespace resolves and imports.

These guard the packaging itself — that ``oaknut`` and ``oaknut.econet`` work
as namespace packages and ``oaknut.econet.core`` is importable with a version.
The behavioural tests for the core types live alongside this file.
"""

import importlib


def test_core_package_imports():
    module = importlib.import_module("oaknut.econet.core")
    assert module is not None


def test_core_exposes_version():
    import oaknut.econet.core as core

    assert isinstance(core.__version__, str)
    assert core.__version__.count(".") >= 2  # semver-ish, e.g. "12.5.3"


def test_econet_is_a_namespace_package_without_init():
    """oaknut.econet must stay a namespace package (no __init__ of its own)."""
    import oaknut.econet as econet

    # A PEP 420 namespace package has no single __file__; its __path__ is a
    # namespace path that other distributions can extend.
    assert getattr(econet, "__file__", None) is None

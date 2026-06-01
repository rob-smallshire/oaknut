"""Smoke tests for the oaknut-econet-aun package and its namespace wiring.

These confirm that two distributions (oaknut-econet-core and oaknut-econet-aun)
contribute to the same oaknut.econet namespace without colliding.
"""

import importlib


def test_aun_package_imports():
    module = importlib.import_module("oaknut.econet.aun")
    assert isinstance(module.__version__, str)


def test_core_is_importable_alongside_aun():
    core = importlib.import_module("oaknut.econet.core")
    assert hasattr(core, "EconetTransport")


def test_econet_remains_a_namespace_package():
    import oaknut.econet as econet

    assert getattr(econet, "__file__", None) is None

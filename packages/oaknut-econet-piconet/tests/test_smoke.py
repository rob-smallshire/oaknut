"""Smoke tests for the oaknut-econet-piconet package and namespace wiring."""

import importlib


def test_piconet_package_imports():
    module = importlib.import_module("oaknut.econet.piconet")
    assert isinstance(module.__version__, str)


def test_core_is_importable_alongside_piconet():
    core = importlib.import_module("oaknut.econet.core")
    assert hasattr(core, "EconetTransport")


def test_econet_remains_a_namespace_package():
    import oaknut.econet as econet

    assert getattr(econet, "__file__", None) is None

"""Smoke tests for the oaknut-econet-kvstore package and namespace wiring."""

import importlib


def test_kvstore_package_imports():
    module = importlib.import_module("oaknut.econet.kvstore")
    assert isinstance(module.__version__, str)


def test_station_is_importable_alongside_kvstore():
    station = importlib.import_module("oaknut.econet.station")
    assert hasattr(station, "Station")


def test_econet_remains_a_namespace_package():
    import oaknut.econet as econet

    assert getattr(econet, "__file__", None) is None

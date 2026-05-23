"""Backwards-compatibility cover for the AcornMeta field rename (#32).

The fields ``load_addr`` / ``exec_addr`` / ``attr`` were renamed to
``load_address`` / ``exec_address`` / ``access`` for consistency with
the rest of the API. The old names are kept as deprecated aliases
for one release; this test pins their behaviour so the alias layer
cannot regress silently.
"""

from __future__ import annotations

import warnings

import pytest
from oaknut.file import AcornMeta


class TestConstructorAliases:
    @pytest.mark.parametrize(
        "old, new, value",
        [
            ("load_addr", "load_address", 0x1900),
            ("exec_addr", "exec_address", 0x8023),
            ("attr", "access", 0x03),
        ],
    )
    def test_old_kwarg_warns_and_sets_new_field(
        self, old: str, new: str, value: int
    ) -> None:
        with pytest.warns(DeprecationWarning, match=f"AcornMeta\\({old}=\\)"):
            meta = AcornMeta(**{old: value})
        assert getattr(meta, new) == value

    def test_new_kwarg_does_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            AcornMeta(load_address=0x1900, exec_address=0x8023, access=0x03)


class TestPropertyAliases:
    def test_load_addr_get_warns_and_returns_load_address(self) -> None:
        meta = AcornMeta(load_address=0x1900)
        with pytest.warns(DeprecationWarning, match="AcornMeta.load_addr"):
            value = meta.load_addr
        assert value == 0x1900

    def test_load_addr_set_warns_and_updates_load_address(self) -> None:
        meta = AcornMeta()
        with pytest.warns(DeprecationWarning, match="AcornMeta.load_addr"):
            meta.load_addr = 0x1900
        assert meta.load_address == 0x1900

    def test_exec_addr_get_warns(self) -> None:
        meta = AcornMeta(exec_address=0x8023)
        with pytest.warns(DeprecationWarning, match="AcornMeta.exec_addr"):
            value = meta.exec_addr
        assert value == 0x8023

    def test_attr_get_warns(self) -> None:
        meta = AcornMeta(access=0x03)
        with pytest.warns(DeprecationWarning, match="AcornMeta.attr"):
            value = meta.attr
        assert value == 0x03

    def test_attr_set_warns(self) -> None:
        meta = AcornMeta()
        with pytest.warns(DeprecationWarning, match="AcornMeta.attr"):
            meta.attr = 0x03
        assert meta.access == 0x03

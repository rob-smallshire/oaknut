"""Tests for copy_file — cross-filesystem file copy via duck-typed paths."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from oaknut.file.copy import copy_file


@dataclass
class FakeStat:
    load_address: int = 0
    exec_address: int = 0
    locked: bool = False
    length: int = 0
    is_directory: bool = False


class FakePath:
    """Minimal duck-typed path for testing copy_file."""

    def __init__(self, name: str, data: bytes | None = None, *, is_dir: bool = False):
        self._name = name
        self._data = data
        self._is_dir = is_dir
        self.load_address = 0
        self.exec_address = 0
        self.locked = False
        self._written = False

    @property
    def name(self) -> str:
        return self._name

    def exists(self) -> bool:
        return self._data is not None or self._is_dir

    def is_dir(self) -> bool:
        return self._is_dir

    def read_bytes(self) -> bytes:
        assert self._data is not None
        return self._data

    def stat(self) -> FakeStat:
        return FakeStat(
            load_address=self.load_address,
            exec_address=self.exec_address,
            locked=self.locked,
            length=len(self._data) if self._data else 0,
        )

    def write_bytes(
        self, data: bytes, *, load_address: int = 0, exec_address: int = 0, **kwargs
    ) -> None:
        self._data = data
        self.load_address = load_address
        self.exec_address = exec_address
        self._written = True


class TestCopyFile:
    def test_copies_data(self) -> None:
        src = FakePath("Hello", b"hello world")
        dst = FakePath("Copy")
        copy_file(src, dst)
        assert dst.read_bytes() == b"hello world"

    def test_preserves_load_address(self) -> None:
        src = FakePath("Hello", b"data")
        src.load_address = 0x1900
        dst = FakePath("Copy")
        copy_file(src, dst)
        assert dst.load_address == 0x1900

    def test_preserves_exec_address(self) -> None:
        src = FakePath("Hello", b"data")
        src.exec_address = 0x8023
        dst = FakePath("Copy")
        copy_file(src, dst)
        assert dst.exec_address == 0x8023

    def test_rejects_directory_source(self) -> None:
        src = FakePath("Dir", is_dir=True)
        dst = FakePath("Copy")
        with pytest.raises(ValueError, match="directory"):
            copy_file(src, dst)

    def test_rejects_nonexistent_source(self) -> None:
        src = FakePath("Ghost")
        dst = FakePath("Copy")
        with pytest.raises(FileNotFoundError):
            copy_file(src, dst)


class TestUnifiedAccess:
    """``copy_file`` passes ``access=`` uniformly to every destination.

    Cover for issue #25: after write_bytes was unified to take ``access``
    (a canonical :class:`oaknut.file.Access` flag, a bool, or None) on
    every path class, ``copy_file`` no longer has to dispatch on the
    destination's filesystem family — it computes the source access
    once and hands the same value to every destination.
    """

    def test_access_kwarg_passed_to_destination(self) -> None:
        from oaknut.file import Access

        src = FakePath("Hello", b"data")
        src.locked = True
        dst = FakePath("Copy")
        captured: dict = {}

        def capture(data: bytes, **kwargs):
            captured.update(kwargs)
            FakePath.write_bytes(dst, data, **{k: kwargs[k] for k in ("load_address", "exec_address")})

        dst.write_bytes = capture  # type: ignore[assignment]
        copy_file(src, dst)
        assert "access" in captured
        assert isinstance(captured["access"], Access)
        assert captured["access"] & Access.L

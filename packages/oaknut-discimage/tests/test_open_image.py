"""Tests for the shared open_image_mmap helper.

The contract: writable when the host file is writable, read-only
fallback when the host file is read-only, and any mutation through
the read-only mmap raises the standard mmap exception.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from oaknut.discimage.open_image import open_image_mmap


def test_writable_file_yields_writable_mmap(tmp_path: Path) -> None:
    filepath = tmp_path / "rw.img"
    filepath.write_bytes(b"\x00" * 512)
    with open_image_mmap(filepath) as (mm, writable):
        assert writable
        mm[0] = 0x42
    assert filepath.read_bytes()[0] == 0x42


def test_readonly_file_yields_readonly_mmap(tmp_path: Path) -> None:
    filepath = tmp_path / "ro.img"
    filepath.write_bytes(b"\x00" * 512)
    filepath.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        with open_image_mmap(filepath) as (mm, writable):
            assert not writable
            with pytest.raises((TypeError, ValueError)):
                mm[0] = 0x42
    finally:
        filepath.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_readonly_file_round_trips_unchanged(tmp_path: Path) -> None:
    filepath = tmp_path / "ro.img"
    original = bytes(range(256)) * 2
    filepath.write_bytes(original)
    filepath.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        with open_image_mmap(filepath) as (mm, writable):
            assert not writable
            assert bytes(mm) == original
    finally:
        filepath.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        with open_image_mmap(tmp_path / "nope.img"):
            pass

"""Tests for extended attribute read/write.

Tests are platform-gated: macOS uses the ``xattr`` package, Linux
uses ``os.setxattr``. Other platforms skip these tests.
"""

import sys

import pytest
from oaknut.file.access import Access
from oaknut.file.meta import AcornMeta
from oaknut.file.xattr import (
    read_acorn_xattrs,
    read_econet_xattrs,
    write_acorn_xattrs,
    write_econet_xattrs,
)

pytestmark = pytest.mark.skipif(
    sys.platform not in ("darwin", "linux"),
    reason="xattrs only supported on macOS and Linux",
)


@pytest.fixture
def host_file(tmp_path):
    """Create an empty host file for xattr testing."""
    filepath = tmp_path / "data.bin"
    filepath.write_bytes(b"test data")
    return filepath


class TestWriteAcornXattrs:

    def test_write_basic(self, host_file):
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023)
        meta = read_acorn_xattrs(host_file)
        assert meta is not None
        assert meta.load_addr == 0x1900
        assert meta.exec_addr == 0x8023

    def test_write_with_attr(self, host_file):
        write_acorn_xattrs(
            host_file, load_addr=0x1900, exec_addr=0x8023, attr=0x0B,
        )
        meta = read_acorn_xattrs(host_file)
        assert meta.attr == 0x0B

    def test_write_without_attr(self, host_file):
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023)
        meta = read_acorn_xattrs(host_file)
        assert meta.attr is None

    def test_write_filetype_stamped(self, host_file):
        write_acorn_xattrs(
            host_file, load_addr=0xFFFFFB00, exec_addr=0,
        )
        meta = read_acorn_xattrs(host_file)
        assert meta.is_filetype_stamped is True
        assert meta.infer_filetype() == 0xFFB

    def test_write_overwrites(self, host_file):
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023)
        write_acorn_xattrs(host_file, load_addr=0x2000, exec_addr=0x3000)
        meta = read_acorn_xattrs(host_file)
        assert meta.load_addr == 0x2000


class TestReadAcornXattrs:

    def test_read_no_xattrs_returns_none(self, host_file):
        assert read_acorn_xattrs(host_file) is None

    def test_read_returns_acorn_meta(self, host_file):
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023)
        meta = read_acorn_xattrs(host_file)
        assert isinstance(meta, AcornMeta)

    def test_read_falls_back_to_econet(self, host_file):
        """When user.acorn.* is absent, fall back to user.econet_*."""
        write_econet_xattrs(host_file, load_addr=0xFFFFDD00, exec_addr=0xFFFFDD00, attr=0x17)
        meta = read_acorn_xattrs(host_file)
        assert meta is not None
        assert meta.load_addr == 0xFFFFDD00
        assert meta.attr == 0x17

    def test_acorn_takes_precedence_over_econet(self, host_file):
        """When both are present, user.acorn.* wins."""
        write_econet_xattrs(host_file, load_addr=0x1111, exec_addr=0x2222, attr=0x17)
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023, attr=0x03)
        meta = read_acorn_xattrs(host_file)
        assert meta.load_addr == 0x1900
        assert meta.attr == 0x03


class TestWriteEconetXattrs:

    def test_write_basic(self, host_file):
        write_econet_xattrs(host_file, load_addr=0xFFFFDD00, exec_addr=0xFFFFDD00)
        meta = read_econet_xattrs(host_file)
        assert meta is not None
        assert meta.load_addr == 0xFFFFDD00

    def test_write_with_perm(self, host_file):
        write_econet_xattrs(
            host_file, load_addr=0x1900, exec_addr=0x8023, attr=0x17,
        )
        meta = read_econet_xattrs(host_file)
        assert meta.attr == 0x17

    def test_default_perm(self, host_file):
        """When attr is None, write_econet_xattrs uses 0x17 default."""
        write_econet_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023)
        meta = read_econet_xattrs(host_file)
        assert meta.attr == 0x17


class TestReadEconetXattrs:

    def test_read_no_xattrs_returns_none(self, host_file):
        assert read_econet_xattrs(host_file) is None

    def test_read_returns_acorn_meta(self, host_file):
        write_econet_xattrs(host_file, load_addr=0xFFFFDD00, exec_addr=0xFFFFDD00)
        meta = read_econet_xattrs(host_file)
        assert isinstance(meta, AcornMeta)


class TestRoundTrip:

    def test_acorn_round_trip(self, host_file):
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0x8023, attr=0x0B)
        meta = read_acorn_xattrs(host_file)
        assert meta.load_addr == 0x1900
        assert meta.exec_addr == 0x8023
        assert meta.attr == 0x0B

    def test_econet_round_trip(self, host_file):
        write_econet_xattrs(host_file, load_addr=0xFFFFDD00, exec_addr=0x12345, attr=0x17)
        meta = read_econet_xattrs(host_file)
        assert meta.load_addr == 0xFFFFDD00
        assert meta.exec_addr == 0x12345
        assert meta.attr == 0x17

    def test_access_flags_round_trip(self, host_file):
        flags = Access.R | Access.W | Access.L
        write_acorn_xattrs(host_file, load_addr=0x1900, exec_addr=0, attr=int(flags))
        meta = read_acorn_xattrs(host_file)
        assert Access(meta.attr) == flags

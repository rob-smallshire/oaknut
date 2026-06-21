"""ADFS Filetyped / Datestamped capability tests.

On ADFS both live inside the 32-bit load/exec fields under the 0xFFF
marker, so setting one must preserve the other, and adopting the marker
on a previously-addressed file uses deterministic defaults.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from oaknut.adfs import ADFS, ADFS_S
from oaknut.filesystem import (
    Datestamped,
    Filetyped,
    create_filesystem,
    reader_for,
)

_WHEN = datetime(2024, 3, 1, 14, 22, 8, 50_000)


def _make_image(tmp_path):
    image_filepath = tmp_path / "test.ads"
    with ADFS.create_file(str(image_filepath), ADFS_S, title="TESTDISC") as adfs:
        # A plain addressed file (BBC default load/exec).
        (adfs.root / "$.PLAIN").write_bytes(
            b"plain", load_address=0x1900, exec_address=0x8023
        )
    return image_filepath


def _mount(image_filepath, *, writable=False):
    filesystem = create_filesystem("adfs")
    reader = reader_for(image_filepath, writable=writable).__enter__()
    mount = filesystem.open(reader, filesystem.probe(reader).geometry)
    return reader, mount


class TestCapabilities:
    def test_mount_provides_both(self, tmp_path):
        reader, mount = _mount(_make_image(tmp_path))
        try:
            assert isinstance(mount, Filetyped)
            assert isinstance(mount, Datestamped)
        finally:
            reader.__exit__(None, None, None)

    def test_resolution_is_centiseconds(self, tmp_path):
        reader, mount = _mount(_make_image(tmp_path))
        try:
            assert mount.datestamp_resolution == timedelta(milliseconds=10)
        finally:
            reader.__exit__(None, None, None)


class TestPlainFile:
    def test_unstamped_reads_none(self, tmp_path):
        reader, mount = _mount(_make_image(tmp_path))
        try:
            assert mount.filetype("$.PLAIN") is None
            assert mount.datestamp("$.PLAIN") is None
        finally:
            reader.__exit__(None, None, None)


class TestSetFiletype:
    def test_round_trips_and_defaults_date_to_epoch(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_filetype("$.PLAIN", 0xFFB)  # BASIC
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.filetype("$.PLAIN") == 0xFFB
            # Un-stamped before, so the date is the deterministic epoch.
            assert mount.datestamp("$.PLAIN") == datetime(1900, 1, 1)
        finally:
            reader.__exit__(None, None, None)


class TestSetDatestamp:
    def test_round_trips_and_defaults_type_to_data(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_datestamp("$.PLAIN", _WHEN)
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.datestamp("$.PLAIN") == _WHEN
            # Un-stamped before, so the filetype defaults to Data (&FFD).
            assert mount.filetype("$.PLAIN") == 0xFFD
        finally:
            reader.__exit__(None, None, None)


class TestOrthogonalPreservation:
    def test_set_filetype_preserves_date(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_datestamp("$.PLAIN", _WHEN)
            mount.set_filetype("$.PLAIN", 0xFEB)  # Obey, date must survive
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.filetype("$.PLAIN") == 0xFEB
            assert mount.datestamp("$.PLAIN") == _WHEN
        finally:
            reader.__exit__(None, None, None)

    def test_set_datestamp_preserves_filetype(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_filetype("$.PLAIN", 0xFF9)  # Sprite
            later = datetime(2090, 6, 1, 9, 0, 0)
            mount.set_datestamp("$.PLAIN", later)
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.filetype("$.PLAIN") == 0xFF9
            assert mount.datestamp("$.PLAIN") == datetime(2090, 6, 1, 9, 0, 0)
        finally:
            reader.__exit__(None, None, None)

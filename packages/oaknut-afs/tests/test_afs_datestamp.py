"""AFS Datestamped capability tests.

AFS keeps a native per-entry date with calendar-day resolution, held
separately from the load/exec addresses (which stay real addresses), so
AFS provides Datestamped but not Filetyped.
"""

from __future__ import annotations

import shutil
from datetime import datetime

import pytest
from oaknut.afs.exceptions import AFSError
from oaknut.filesystem import (
    Datestamped,
    Filetyped,
    create_filesystem,
    reader_for,
    region_reader,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"


def _afs_region_reader(reader):
    identification = create_filesystem("adfs").probe(reader)
    region = identification.reserved_regions[0]
    return region_reader(
        reader, identification.geometry, region.start_sector, region.num_sectors
    )


def _writable_copy(tmp_path):
    image_filepath = tmp_path / "l3fs.dat"
    shutil.copy(_L3FS_DAT, image_filepath)
    return image_filepath


class TestCapabilities:
    def test_datestamped_but_not_filetyped(self):
        with reader_for(_L3FS_DAT) as reader:
            mount = create_filesystem("afs").open(_afs_region_reader(reader))
            assert isinstance(mount, Datestamped)
            assert not isinstance(mount, Filetyped)

    def test_resolution_is_a_day(self):
        from datetime import timedelta

        with reader_for(_L3FS_DAT) as reader:
            mount = create_filesystem("afs").open(_afs_region_reader(reader))
            assert mount.datestamp_resolution == timedelta(days=1)


class TestRoundTrip:
    def test_set_and_read_back_drops_time_of_day(self, tmp_path):
        image_filepath = _writable_copy(tmp_path)
        afs = create_filesystem("afs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = afs.open(_afs_region_reader(reader))
            mount.write_bytes("$.DATEME", b"data")
            mount.set_datestamp("$.DATEME", datetime(2005, 6, 15, 14, 30, 0))
        with reader_for(image_filepath) as reader:
            mount = afs.open(_afs_region_reader(reader))
            # Day resolution: the time of day is not stored.
            assert mount.datestamp("$.DATEME") == datetime(2005, 6, 15)

    def test_set_datestamp_preserves_load_exec(self, tmp_path):
        from oaknut.file import AcornMeta

        image_filepath = _writable_copy(tmp_path)
        afs = create_filesystem("afs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = afs.open(_afs_region_reader(reader))
            mount.write_bytes("$.KEEP", b"data")
            mount.set_acorn_meta(
                "$.KEEP", AcornMeta(load_address=0x8000, exec_address=0x9000, access=0)
            )
            mount.set_datestamp("$.KEEP", datetime(2001, 1, 1))
        with reader_for(image_filepath) as reader:
            mount = afs.open(_afs_region_reader(reader))
            meta = mount.acorn_meta("$.KEEP")
            assert meta.load_address == 0x8000  # untouched by the datestamp
            assert meta.exec_address == 0x9000


class TestRange:
    @pytest.mark.parametrize("year", [1970, 2200])
    def test_year_outside_afs_range_errors_cleanly(self, tmp_path, year):
        image_filepath = _writable_copy(tmp_path)
        afs = create_filesystem("afs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = afs.open(_afs_region_reader(reader))
            mount.write_bytes("$.OOR", b"data")
            with pytest.raises(AFSError):
                mount.set_datestamp("$.OOR", datetime(year, 1, 1))

"""A side's usable extent: the catalogue's sector count, capped by the image (#96).

The catalogue's count and the image's size can disagree in both
directions. A count larger than the image is sound (a trimmed image, or an
original duplicated onto fewer tracks than it was mastered for, like side
2 of Dunjunz), so validation stays silent; a count smaller than the image
is what a real DFS honours. Either way size, free space, the free map and
allocation must all describe the same extent, and stat says when the two
disagree.
"""

from __future__ import annotations

import pytest
from oaknut.dfs.exceptions import DiscFullError
from oaknut.filesystem import identify, reader_for
from oaknut.filesystem.coordinator import create_filesystem


def _image(tmp_path, *, image_tracks: int, declared_sectors: int, used_sectors: int = 0):
    """An Acorn DFS side of *image_tracks* tracks whose catalogue declares
    *declared_sectors*, holding one file of *used_sectors* sectors."""
    from oaknut.dfs import ACORN_DFS_40T_SINGLE_SIDED, ACORN_DFS_80T_SINGLE_SIDED, DFS

    disc_format = ACORN_DFS_80T_SINGLE_SIDED if image_tracks == 80 else ACORN_DFS_40T_SINGLE_SIDED
    filepath = tmp_path / "side.ssd"
    with DFS.create_file(filepath, disc_format, title="EXTENT") as dfs:
        if used_sectors:
            (dfs.root / "$.DATA").write_bytes(bytes(used_sectors * 256))
    data = bytearray(filepath.read_bytes())
    data[0x106] = (data[0x106] & ~0x03) | (declared_sectors >> 8)
    data[0x107] = declared_sectors & 0xFF
    filepath.write_bytes(bytes(data))
    return filepath


def _mount(filepath, *, writable: bool = False):
    best = identify(filepath)[0]
    reader = reader_for(filepath, writable=writable)
    return create_filesystem(best.filesystem).open(reader, best.geometry)


class TestCountLargerThanImage:
    def test_size_and_free_describe_the_image(self, tmp_path):
        mount = _mount(_image(tmp_path, image_tracks=40, declared_sectors=800, used_sectors=100))
        assert mount.size_bytes() == 400 * 256
        assert mount.free_bytes() == (400 - 2 - 100) * 256

    def test_free_map_covers_only_sectors_that_exist(self, tmp_path):
        mount = _mount(_image(tmp_path, image_tracks=40, declared_sectors=800, used_sectors=100))
        free_map = mount.free_map()
        assert free_map.total_sectors == 400
        assert free_map.free_regions == ((102, 298),)

    def test_stat_notes_the_disagreement(self, tmp_path):
        mount = _mount(_image(tmp_path, image_tracks=40, declared_sectors=800))
        (note,) = mount.status_notes()
        assert "800" in note and "400" in note

    def test_validation_stays_silent(self, tmp_path):
        mount = _mount(_image(tmp_path, image_tracks=40, declared_sectors=800))
        assert mount.validate() == []


class TestCountSmallerThanImage:
    def test_size_free_and_map_follow_the_catalogue(self, tmp_path):
        mount = _mount(_image(tmp_path, image_tracks=80, declared_sectors=400, used_sectors=100))
        assert mount.size_bytes() == 400 * 256
        assert mount.free_bytes() == (400 - 2 - 100) * 256
        assert mount.free_map().total_sectors == 400
        assert mount.free_map().free_regions == ((102, 298),)

    def test_allocation_stops_at_the_catalogue_count(self, tmp_path):
        mount = _mount(
            _image(tmp_path, image_tracks=80, declared_sectors=400, used_sectors=100),
            writable=True,
        )
        with pytest.raises(DiscFullError):
            mount.write_bytes("$.BIG", bytes(299 * 256))
        mount.write_bytes("$.FITS", bytes(298 * 256))

    def test_stat_notes_the_disagreement(self, tmp_path):
        mount = _mount(_image(tmp_path, image_tracks=80, declared_sectors=400))
        (note,) = mount.status_notes()
        assert "400" in note and "800" in note


def test_an_agreeing_disc_has_no_note(tmp_path):
    mount = _mount(_image(tmp_path, image_tracks=80, declared_sectors=800))
    assert mount.status_notes() == ()

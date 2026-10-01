"""A directory write that fails part-way leaves the disc unchanged (#79).

The directory serialisers write field by field and encode the title near
the end, so a title the format cannot encode used to fail after the
entries had been overwritten, leaving a half-written directory that no
longer parsed.
"""

from __future__ import annotations

import pytest
from oaknut.adfs import ADFS, ADFS_F, ADFS_L, ADFS_S


def _image_bytes(adfs: ADFS) -> bytes:
    return bytes(adfs._disc._disc_image.buffer)


@pytest.mark.parametrize(
    ("disc_format", "title"),
    [
        (ADFS_S, "CAFÉ"),  # old directories hold ASCII titles
        (ADFS_L, "CAFÉ"),
        (ADFS_F, "Ā"),  # New directories hold Latin-1 titles
    ],
    ids=["S", "L", "F"],
)
class TestUnencodableTitle:
    def _disc(self, disc_format) -> ADFS:
        adfs = ADFS.create(disc_format)
        (adfs.root / "FILE").write_bytes(b"data")
        adfs.title = "BEFORE"
        return adfs

    def test_the_image_is_unchanged(self, disc_format, title):
        adfs = self._disc(disc_format)
        before = _image_bytes(adfs)
        with pytest.raises(ValueError):
            adfs.title = title
        assert _image_bytes(adfs) == before

    def test_the_disc_still_reads(self, disc_format, title):
        adfs = self._disc(disc_format)
        with pytest.raises(ValueError):
            adfs.title = title
        reopened = ADFS.from_buffer(adfs._disc._disc_image.buffer)
        assert reopened.title == "BEFORE"
        assert [child.name for child in reopened.root] == ["FILE"]

    def test_a_subdirectory_title_is_unchanged_too(self, disc_format, title):
        adfs = self._disc(disc_format)
        (adfs.root / "DIR").mkdir()
        before = _image_bytes(adfs)
        with pytest.raises(ValueError):
            (adfs.root / "DIR").title = title
        assert _image_bytes(adfs) == before

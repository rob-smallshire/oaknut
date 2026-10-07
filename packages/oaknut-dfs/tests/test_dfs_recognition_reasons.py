"""DFS says why it declines an image (#82).

Each check the Acorn and Watford catalogue recognition makes gives a
user-interpretable reason when it fails, naming the byte and its value.
The images are built from scratch: a fresh, valid catalogue with one
field corrupted.
"""

from __future__ import annotations

import pytest
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED
from oaknut.filesystem import Identification, Rejection, create_filesystem, reader_for


def _fresh(disc_format=ACORN_DFS_80T_SINGLE_SIDED) -> bytearray:
    dfs = DFS.create(disc_format, title="TITLE")
    return bytearray(dfs._catalogued_surface._surface._disc_image.buffer)


def _verdict(name: str, image: bytes):
    with reader_for(bytes(image)) as reader:
        return create_filesystem(name).probe(reader)


def _reason(name: str, image: bytes) -> str:
    verdict = _verdict(name, image)
    assert isinstance(verdict, Rejection), verdict
    assert verdict.filesystem == name
    return verdict.reason


class TestAcornDFS:
    def test_a_valid_catalogue_is_still_identified(self):
        assert isinstance(_verdict("acorn-dfs", _fresh()), Identification)

    def test_too_small(self):
        assert "too small" in _reason("acorn-dfs", b"\x00" * 256)

    def test_title_byte_with_top_bit(self):
        image = _fresh()
        image[3] = 0xC1
        assert _reason("acorn-dfs", image) == (
            "catalogue title byte &C1 at &003 has its top bit set"
        )

    def test_file_count_not_a_multiple_of_8(self):
        image = _fresh()
        image[0x105] = 0x0D
        assert _reason("acorn-dfs", image) == ("file count byte &0D at &105 is not a multiple of 8")

    def test_reserved_bits_in_the_boot_byte(self):
        image = _fresh()
        image[0x106] |= 0x40
        assert "&106" in _reason("acorn-dfs", image)
        assert "reserved bits" in _reason("acorn-dfs", image)

    def test_implausible_sector_count_with_no_files_to_corroborate(self):
        image = _fresh()
        image[0x106] &= ~0x03
        image[0x107] = 3
        reason = _reason("acorn-dfs", image)
        assert "declares 3 sectors" in reason
        assert "no files" in reason

    def test_a_watford_disc_is_left_to_watford(self):
        image = _fresh(WATFORD_DFS_80T_SINGLE_SIDED)
        assert "Watford" in _reason("acorn-dfs", image)


class TestWatfordDFS:
    def test_a_valid_catalogue_is_still_identified(self):
        assert isinstance(
            _verdict("watford-dfs", _fresh(WATFORD_DFS_80T_SINGLE_SIDED)), Identification
        )

    def test_an_acorn_disc_lacks_the_marker(self):
        assert _reason("watford-dfs", _fresh()) == (
            "no Watford marker: sector 2 does not start with eight &AA bytes"
        )

    def test_too_small(self):
        assert "too small" in _reason("watford-dfs", b"\x00" * 512)

    def test_file_count_not_a_multiple_of_8(self):
        image = _fresh(WATFORD_DFS_80T_SINGLE_SIDED)
        image[0x105] = 0x0D
        assert _reason("watford-dfs", image) == (
            "file count byte &0D at &105 is not a multiple of 8"
        )

    def test_mismatched_section_headers(self):
        image = _fresh(WATFORD_DFS_80T_SINGLE_SIDED)
        image[0x307] ^= 0x10
        assert "disagree" in _reason("watford-dfs", image)


@pytest.mark.parametrize("name", ["acorn-dfs", "watford-dfs"])
def test_every_check_gives_a_reason_for_garbage(name):
    reason = _reason(name, b"\xff" * 204800)
    assert reason and reason != "not recognised"

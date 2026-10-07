"""ADFS says why it declines an image (#82)."""

from __future__ import annotations

from oaknut.adfs import ADFS, ADFS_L
from oaknut.filesystem import Identification, Rejection, create_filesystem, reader_for


def _verdict(image: bytes):
    with reader_for(bytes(image)) as reader:
        return create_filesystem("adfs").probe(reader)


def _reason(image: bytes) -> str:
    verdict = _verdict(image)
    assert isinstance(verdict, Rejection), verdict
    assert verdict.filesystem == "adfs"
    return verdict.reason


def test_a_valid_disc_is_still_identified():
    image = bytes(ADFS.create(ADFS_L)._disc._disc_image.buffer)
    assert isinstance(_verdict(image), Identification)


def test_too_small():
    assert _reason(b"\x00" * 300) == (
        "image too small for an ADFS free-space map: 300 bytes, needs 512"
    )


def test_bad_map_checksums_name_the_stored_and_computed_values():
    assert _reason(b"\xff" * 204800) == (
        "free-space map sector 0 checksum is &FF but the sector sums to &FE; "
        "free-space map sector 1 checksum is &FF but the sector sums to &FE"
    )


def test_a_missing_root_directory_names_the_expected_signatures():
    assert _reason(b"\x00" * 204800) == (
        "no ADFS root directory: expected 'Hugo' at &201 or 'Hugo'/'Nick' at &401, "
        "found 00 00 00 00 and 00 00 00 00"
    )

"""ROMFS identification must not claim disc images (#94).

A DFS catalogue's name bytes can pass for a paged-ROM header, and a large
image holds enough bytes that some ``&2A`` happens to start a block with a
valid header CRC. A paged ROM is at most 16 KiB, and the MOS only accepts
one whose copyright string begins ``(C)``.
"""

from __future__ import annotations

import pytest
from oaknut.filesystem import Confidence, Rejection, identify, reader_for
from oaknut.romfs.filesystem import AcornROMFS
from oaknut.romfs.romfs import build_rom_image

from tests.fixtures import BEEBEM_IMAGES_DIRPATH, REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"

#: Disc images the probe used to claim with PROBABLE confidence.
FALSE_POSITIVE_FILEPATHS = [
    BEEBEM_IMAGES_DIRPATH / "Games.ssd",
    BEEBEM_IMAGES_DIRPATH / "L3-Utils.dsd",
    BEEBEM_IMAGES_DIRPATH / "Torch_standard_utilities_2.dsd",
    REFERENCE_IMAGES_DIRPATH / "owlet" / "owlet-dla.ssd",
]


@pytest.mark.parametrize("filepath", FALSE_POSITIVE_FILEPATHS, ids=lambda p: p.name)
def test_disc_images_are_rejected(filepath):
    verdict = AcornROMFS().probe(reader_for(filepath))
    assert isinstance(verdict, Rejection)
    assert "16 KiB" in verdict.reason


@pytest.mark.parametrize("filepath", FALSE_POSITIVE_FILEPATHS, ids=lambda p: p.name)
def test_identify_offers_no_romfs_candidate(filepath):
    assert "acorn-romfs" not in [c.filesystem for c in identify(filepath)]


def test_a_rom_padded_past_16_kib_is_rejected():
    image = (ROMFS_DIRPATH / "Electron_Hopper.rom").read_bytes() + b"\xff"
    assert isinstance(AcornROMFS().probe(reader_for(image)), Rejection)


@pytest.mark.parametrize("size", [8 * 1024, 16 * 1024])
def test_both_bank_sizes_are_still_recognised(size):
    image = build_rom_image(title="SMALL", size=size)
    verdict = AcornROMFS().probe(reader_for(image))
    assert verdict.confidence == Confidence.STRONG


def test_without_a_copyright_marker_it_is_only_possible():
    image = bytearray((ROMFS_DIRPATH / "Electron_Hopper.rom").read_bytes())
    copyright_offset = image[7] + 1
    assert image[copyright_offset : copyright_offset + 3] == b"(C)"
    image[copyright_offset : copyright_offset + 3] = b"(X)"
    verdict = AcornROMFS().probe(reader_for(bytes(image)))
    assert verdict.confidence == Confidence.POSSIBLE
    assert any("(C)" in line for line in verdict.evidence)


def test_every_reference_rom_is_still_strong():
    for filepath in sorted(ROMFS_DIRPATH.glob("*.rom")):
        verdict = AcornROMFS().probe(reader_for(filepath))
        assert verdict.confidence == Confidence.STRONG, filepath.name

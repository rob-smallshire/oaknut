"""The one analysis of a DFS catalogue's sector-count field (#84).

Recognition, sizing and validation all call ``sector_count_defect``, so
each cause of a malformed count is pinned here once.
"""

from __future__ import annotations

import pytest
from oaknut.dfs.acorn_dfs_catalogue import sector_count_defect
from oaknut.dfs.exceptions import MalformedSectorCountError


def _sector1(byte6: int, low: int, files: tuple[tuple[int, int], ...] = ()) -> bytearray:
    """Catalogue sector 1 with the given count bytes and (start, sectors) files."""
    sector1 = bytearray(256)
    sector1[5] = len(files) * 8
    sector1[6], sector1[7] = byte6, low
    for index, (start, sectors) in enumerate(files):
        offset = 8 + index * 8
        length = sectors * 256
        sector1[offset + 4], sector1[offset + 5] = length & 0xFF, (length >> 8) & 0xFF
        sector1[offset + 6] = ((length >> 12) & 0x30) | ((start >> 8) & 0x03)
        sector1[offset + 7] = start & 0xFF
    return sector1


@pytest.mark.parametrize(
    ("byte6", "low", "files", "cause", "declared"),
    [
        # PanOS 1.40: bit 2 extends the count (Opus's 11-bit form).
        (0x36, 0x40, ((2, 100),), MalformedSectorCountError.EXTENSION_BITS, 1600),
        (0x35, 0xDF, ((2, 100),), MalformedSectorCountError.EXTENSION_BITS, 1503),
        # Owlet: a bogus small total.
        (0x30, 0x03, ((2, 10),), MalformedSectorCountError.IMPLAUSIBLE, 3),
        # A plausible count that files run past, short of the side.
        (0x00, 200, ((2, 300),), MalformedSectorCountError.FILES_RUN_PAST, 200),
    ],
)
def test_each_cause(byte6, low, files, cause, declared):
    defect = sector_count_defect(_sector1(byte6, low, files), side_sectors=800)
    assert isinstance(defect, MalformedSectorCountError)
    assert (defect.cause, defect.declared, defect.side_sectors) == (cause, declared, 800)
    assert "the side holds 800" in str(defect)


@pytest.mark.parametrize(
    ("byte6", "low", "files", "side_sectors"),
    [
        (0x03, 0x20, ((2, 300),), 800),  # a whole 80-track side
        (0x03, 0x20, ((2, 100),), 400),  # a truncated image keeps its full count
        (0x01, 0x90, ((390, 20),), 400),  # a file overruns a full-side count: its defect
    ],
)
def test_sound_counts(byte6, low, files, side_sectors):
    assert sector_count_defect(_sector1(byte6, low, files), side_sectors=side_sectors) is None


def test_only_extension_and_implausible_counts_doubt_the_catalogue():
    extended = sector_count_defect(_sector1(0x36, 0x40))
    run_past = sector_count_defect(_sector1(0x00, 200, ((2, 300),)))
    assert extended.doubts_the_catalogue
    assert not run_past.doubts_the_catalogue

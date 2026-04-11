"""Tests for oaknut.afs.info_sector.

The golden fixture is transcribed from Beebmaster's PDF page 6 (the
"First NFS Sector" hex dump). Every documented field value must
parse correctly, and a round-trip through ``to_bytes`` must produce
the original 256-byte sector.
"""

from __future__ import annotations

import datetime

import pytest
from helpers import beebmaster
from oaknut.afs import AfsDate, AFSInfoSectorError, SystemInternalName
from oaknut.afs.info_sector import (
    INFO_SECTOR_SIZE,
    MAGIC,
    MEDIA_WINCHESTER,
    InfoSector,
    InfoSectorPair,
)

# ---------------------------------------------------------------------------
# Beebmaster PDF golden fixture
# ---------------------------------------------------------------------------


class TestBeebmasterFixture:
    """Every documented field in the PDF's hex dump is decoded correctly."""

    def test_parses_without_error(self) -> None:
        InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)

    def test_disc_name(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.disc_name == beebmaster.INFO_SECTOR_DISC_NAME

    def test_cylinders(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.cylinders == beebmaster.INFO_SECTOR_CYLINDERS

    def test_total_sectors(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.total_sectors == beebmaster.INFO_SECTOR_TOTAL_SECTORS

    def test_num_discs(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.num_discs == beebmaster.INFO_SECTOR_NUM_DISCS

    def test_sectors_per_cylinder(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.sectors_per_cylinder == beebmaster.INFO_SECTOR_SECTORS_PER_CYLINDER

    def test_bitmap_size(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.bitmap_size_sectors == beebmaster.INFO_SECTOR_BITMAP_SIZE

    def test_addition_factor(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.addition_factor == beebmaster.INFO_SECTOR_ADDITION_FACTOR

    def test_drive_increment(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.drive_increment == beebmaster.INFO_SECTOR_DRIVE_INCREMENT

    def test_root_sin(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.root_sin == beebmaster.INFO_SECTOR_ROOT_SIN

    def test_date(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.date.date == beebmaster.INFO_SECTOR_DATE

    def test_start_cylinder(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.start_cylinder == beebmaster.INFO_SECTOR_START_CYLINDER

    def test_media_flag(self) -> None:
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.media_flag == beebmaster.INFO_SECTOR_MEDIA_FLAG

    def test_byte_for_byte_round_trip(self) -> None:
        """Re-serialising the parsed form yields the exact input bytes."""
        info = InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)
        assert info.to_bytes() == beebmaster.INFO_SECTOR_BYTES


# ---------------------------------------------------------------------------
# Construct-from-Python round trip
# ---------------------------------------------------------------------------


class TestPythonRoundTrip:
    """Build from Python values, serialise, parse, compare."""

    def _sample(self) -> InfoSector:
        return InfoSector(
            disc_name="MyTestDisc",
            cylinders=80,
            total_sectors=1280,
            sectors_per_cylinder=16,
            root_sin=SystemInternalName(0x51),
            date=AfsDate(datetime.date(2024, 6, 15)),
            start_cylinder=5,
        )

    def test_round_trip(self) -> None:
        original = self._sample()
        parsed = InfoSector.from_bytes(original.to_bytes())
        assert parsed == original

    def test_to_bytes_is_exactly_one_sector(self) -> None:
        assert len(self._sample().to_bytes()) == INFO_SECTOR_SIZE

    def test_magic_is_first_four_bytes(self) -> None:
        assert self._sample().to_bytes()[:4] == MAGIC

    def test_unused_tail_is_zero(self) -> None:
        tail = self._sample().to_bytes()[39:]
        assert tail == b"\x00" * len(tail)


# ---------------------------------------------------------------------------
# Validation errors on construction
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    @pytest.fixture
    def valid_kwargs(self) -> dict:
        return {
            "disc_name": "Test",
            "cylinders": 80,
            "total_sectors": 1280,
            "sectors_per_cylinder": 16,
            "root_sin": SystemInternalName(0x51),
            "date": AfsDate(datetime.date(2024, 1, 1)),
            "start_cylinder": 5,
        }

    def test_empty_disc_name(self, valid_kwargs: dict) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            InfoSector(**{**valid_kwargs, "disc_name": ""})

    def test_disc_name_too_long(self, valid_kwargs: dict) -> None:
        with pytest.raises(ValueError, match="exceeds 16 characters"):
            InfoSector(**{**valid_kwargs, "disc_name": "A" * 17})

    def test_disc_name_with_space(self, valid_kwargs: dict) -> None:
        with pytest.raises(ValueError, match="non-printable or space"):
            InfoSector(**{**valid_kwargs, "disc_name": "Has Space"})

    def test_total_sectors_overflow(self, valid_kwargs: dict) -> None:
        with pytest.raises(ValueError, match="outside 1..0xFFFFFF"):
            InfoSector(**{**valid_kwargs, "total_sectors": 0x1000000})

    def test_cylinders_zero(self, valid_kwargs: dict) -> None:
        with pytest.raises(ValueError, match="outside 1..65535"):
            InfoSector(**{**valid_kwargs, "cylinders": 0})


# ---------------------------------------------------------------------------
# Parse errors on bad input
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_empty_bytes(self) -> None:
        with pytest.raises(AFSInfoSectorError, match="too short"):
            InfoSector.from_bytes(b"")

    def test_too_short(self) -> None:
        with pytest.raises(AFSInfoSectorError, match="too short"):
            InfoSector.from_bytes(b"\x00" * 10)

    def test_bad_magic(self) -> None:
        bad = b"XXXX" + beebmaster.INFO_SECTOR_BYTES[4:]
        with pytest.raises(AFSInfoSectorError, match="bad magic"):
            InfoSector.from_bytes(bad)

    def test_bad_disc_name_nonascii(self) -> None:
        bad = bytearray(beebmaster.INFO_SECTOR_BYTES)
        bad[4] = 0xFF  # replace 'L' with a non-ASCII byte
        with pytest.raises(AFSInfoSectorError, match="bad disc name"):
            InfoSector.from_bytes(bytes(bad))


# ---------------------------------------------------------------------------
# Length tolerance
# ---------------------------------------------------------------------------


class TestLengthTolerance:
    def test_accepts_exactly_256_bytes(self) -> None:
        InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES)

    def test_accepts_truncated_but_valid(self) -> None:
        """A 39-byte buffer with all fields present is enough to parse."""
        InfoSector.from_bytes(beebmaster.INFO_SECTOR_BYTES[:39])

    def test_accepts_oversized_buffer(self) -> None:
        """Extra trailing bytes are silently ignored."""
        oversized = beebmaster.INFO_SECTOR_BYTES + b"\xab" * 100
        info = InfoSector.from_bytes(oversized)
        assert info.disc_name == beebmaster.INFO_SECTOR_DISC_NAME

    def test_accepts_missing_media_flag(self) -> None:
        """Older producers might write only 38 bytes — default Winchester."""
        truncated = beebmaster.INFO_SECTOR_BYTES[:38]
        info = InfoSector.from_bytes(truncated)
        assert info.media_flag == MEDIA_WINCHESTER


# ---------------------------------------------------------------------------
# InfoSectorPair redundant-copy verification
# ---------------------------------------------------------------------------


class TestInfoSectorPair:
    def test_matching_copies_succeed(self) -> None:
        pair = InfoSectorPair.from_bytes_pair(
            beebmaster.INFO_SECTOR_BYTES,
            beebmaster.INFO_SECTOR_COPY_BYTES,
        )
        assert pair.agreed.disc_name == beebmaster.INFO_SECTOR_DISC_NAME

    def test_mismatched_copies_raise(self) -> None:
        differing = bytearray(beebmaster.INFO_SECTOR_BYTES)
        differing[20] = 0xFF  # change cylinder count in secondary copy
        with pytest.raises(AFSInfoSectorError, match="copies disagree"):
            InfoSectorPair.from_bytes_pair(
                beebmaster.INFO_SECTOR_BYTES,
                bytes(differing),
            )

    def test_both_must_be_parseable(self) -> None:
        with pytest.raises(AFSInfoSectorError, match="bad magic"):
            InfoSectorPair.from_bytes_pair(
                beebmaster.INFO_SECTOR_BYTES,
                b"JUNK" + beebmaster.INFO_SECTOR_BYTES[4:],
            )

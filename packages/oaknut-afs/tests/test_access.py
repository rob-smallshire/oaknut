"""Tests for oaknut.afs.access.AFSAccess.

Fixtures are drawn from Beebmaster's PDF "Example Access Strings and
Their Access Byte" table (pp.13-15). Every documented entry is
exercised as a round-trip: string → byte → string.
"""

from __future__ import annotations

import pytest
from oaknut.afs import AFSAccess

# (access string, byte value, byte in hex) — verbatim from the PDF table.
# Listed in the same order as the document.
EXAMPLES: list[tuple[str, int]] = [
    ("/", 0x00),
    ("/R", 0x01),
    ("/W", 0x02),
    ("/WR", 0x03),
    ("R/", 0x04),
    ("R/R", 0x05),
    ("R/W", 0x06),
    ("R/WR", 0x07),
    ("WR/", 0x0C),
    ("WR/R", 0x0D),
    ("WR/W", 0x0E),
    ("WR/WR", 0x0F),
    ("L/", 0x10),
    ("L/R", 0x11),
    ("L/W", 0x12),
    ("L/WR", 0x13),
    ("LR/", 0x14),
    ("LR/R", 0x15),
    ("LR/W", 0x16),
    ("LR/WR", 0x17),
    ("LWR/", 0x1C),
    ("LWR/R", 0x1D),
    ("LWR/W", 0x1E),
    ("LWR/WR", 0x1F),
    ("D/", 0x20),
    ("DL/", 0x30),
]


@pytest.mark.parametrize("text,byte", EXAMPLES, ids=[t for t, _ in EXAMPLES])
def test_from_string_matches_table(text: str, byte: int) -> None:
    """Parsing each PDF example yields the documented access byte."""
    assert int(AFSAccess.from_string(text)) == byte


@pytest.mark.parametrize("text,byte", EXAMPLES, ids=[t for t, _ in EXAMPLES])
def test_to_string_matches_table(text: str, byte: int) -> None:
    """Formatting each PDF example byte yields the documented string."""
    assert AFSAccess.from_byte(byte).to_string() == text


@pytest.mark.parametrize("text,byte", EXAMPLES, ids=[t for t, _ in EXAMPLES])
def test_round_trip(text: str, byte: int) -> None:
    """Byte → AFSAccess → byte is a no-op."""
    assert AFSAccess.from_byte(byte).to_byte() == byte


class TestDirectoryFlag:
    def test_directory_flag_detected(self) -> None:
        assert AFSAccess.from_string("D/").is_directory
        assert AFSAccess.from_string("DL/").is_directory

    def test_non_directory_flag(self) -> None:
        assert not AFSAccess.from_string("LWR/WR").is_directory
        assert not AFSAccess.from_string("/").is_directory

    def test_locked_flag(self) -> None:
        assert AFSAccess.from_string("L/").is_locked
        assert AFSAccess.from_string("DL/").is_locked
        assert AFSAccess.from_string("LWR/WR").is_locked
        assert not AFSAccess.from_string("WR/WR").is_locked


class TestFromByteIgnoresJunkBits:
    def test_ignores_bits_6_and_7(self) -> None:
        """The ROM ignores bits 6-7 in the on-disc byte; we do too."""
        assert AFSAccess.from_byte(0xC0).to_byte() == 0x00
        assert AFSAccess.from_byte(0xD5).to_byte() == 0x15


class TestCaseInsensitive:
    def test_lowercase_accepted(self) -> None:
        assert AFSAccess.from_string("lwr/wr") == AFSAccess.from_string("LWR/WR")

    def test_mixed_case_accepted(self) -> None:
        assert AFSAccess.from_string("Lr/wR") == AFSAccess.from_string("LR/WR")


class TestParseErrors:
    def test_missing_slash(self) -> None:
        with pytest.raises(ValueError, match="missing '/'"):
            AFSAccess.from_string("LWR")

    def test_unknown_owner_char(self) -> None:
        with pytest.raises(ValueError, match="unexpected character"):
            AFSAccess.from_string("LX/R")

    def test_unknown_public_char(self) -> None:
        with pytest.raises(ValueError, match="unexpected character"):
            AFSAccess.from_string("LR/Q")

    def test_directory_with_public_bits(self) -> None:
        with pytest.raises(ValueError, match="directories take no public"):
            AFSAccess.from_string("D/R")


class TestCompose:
    def test_or_combines(self) -> None:
        composed = (
            AFSAccess.LOCKED | AFSAccess.OWNER_READ | AFSAccess.OWNER_WRITE | AFSAccess.PUBLIC_READ
        )
        assert int(composed) == 0x1D
        assert composed.to_string() == "LWR/R"

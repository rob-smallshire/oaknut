"""Big directory (ADFS E+/F+) reading.

Big directories are the New Map ``+`` formats' variable-size directories:
a header ending in the directory's own long name, fixed 0x1C-byte entries
pointing into a following name heap, and an 8-byte "oven" tail with a
ROR-13 check byte. Object indirect addresses are four bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs.adfs import ADFS, ADFS_E_PLUS, ADFS_F_PLUS
from oaknut.adfs.directory import (
    BigDirectoryFormat,
    _ADFSDirectory,
    _ADFSDirectoryEntry,
    _ADFSRawAttributes,
)
from oaknut.adfs.exceptions import ADFSError

_DIM = Path.home() / "Code" / "DiscImageManager" / "Blank Images" / "Acorn ADFS"


def _att(directory=False):
    return _ADFSRawAttributes(True, True, False, directory, False, True, False, False, False)


def test_big_dir_serialize_parse_round_trip():
    fmt = BigDirectoryFormat()
    entries = (
        _ADFSDirectoryEntry("ShortName", 0xFFFFFD00, 0x12345678, 100, 0x501, 0, _att()),
        _ADFSDirectoryEntry(
            "A_Very_Long_Filename_Beyond_Ten_Chars", 0, 0, 4096, 0x601, 0, _att(True)
        ),
        _ADFSDirectoryEntry("x", 0xFFF00000, 0, 7, 0x701, 0, _att()),
    )
    directory = _ADFSDirectory(
        name="MyBigDir",
        title="",
        parent_address=0x301,
        disc_address=0x501,
        entries=entries,
        sequence_number=5,
        signature=b"SBPr",
        big_dir_size=2048,
    )
    buf = bytearray(2048)
    fmt.serialize(directory, buf)
    assert bytes(buf[4:8]) == b"SBPr"
    assert bytes(buf[2048 - 8 : 2048 - 4]) == b"oven"

    parsed = fmt.parse(buf, 0x501)
    assert parsed.name == "MyBigDir"
    assert parsed.parent_address == 0x301
    assert parsed.sequence_number == 5
    assert parsed.big_dir_size == 2048
    assert [e.name for e in parsed.entries] == [e.name for e in entries]
    for got, want in zip(parsed.entries, entries):
        assert got.load_address == want.load_address
        assert got.exec_address == want.exec_address
        assert got.length == want.length
        assert got.indirect_disc_address == want.indirect_disc_address
        assert got.is_directory == want.is_directory


def test_big_dir_detects_broken_check_byte():
    fmt = BigDirectoryFormat()
    directory = _ADFSDirectory("D", "", 0x301, 0x501, (), 0, b"SBPr", 2048)
    buf = bytearray(2048)
    fmt.serialize(directory, buf)
    buf[2047] ^= 0xFF  # corrupt the check byte
    with pytest.raises(ADFSError):
        fmt.parse(buf, 0x501)


@pytest.mark.skipif(not (_DIM / "ADFS_E+.adf").exists(), reason="DIM E+ blank not present")
def test_read_blank_e_plus():
    with ADFS.from_file(_DIM / "ADFS_E+.adf") as adfs:
        assert adfs.is_new_map
        assert isinstance(adfs._dir_format, BigDirectoryFormat)
        assert adfs._map.disc_record.format_version == 1
        assert adfs._map.disc_record.nzones == 1
        assert list(adfs.root.iterdir()) == []
        assert adfs.validate() == []


@pytest.mark.skipif(not (_DIM / "ADFS_F+.adf").exists(), reason="DIM F+ blank not present")
def test_read_blank_f_plus():
    with ADFS.from_file(_DIM / "ADFS_F+.adf") as adfs:
        assert adfs.is_new_map
        assert isinstance(adfs._dir_format, BigDirectoryFormat)
        assert adfs._map.disc_record.nzones == 4
        assert list(adfs.root.iterdir()) == []
        assert adfs.validate() == []


@pytest.mark.skipif(not (_DIM / "ADFS_E+.adf").exists(), reason="DIM E+ blank not present")
def test_big_dir_check_byte_matches_real_blank():
    raw = (_DIM / "ADFS_E+.adf").read_bytes()
    with ADFS.from_file(_DIM / "ADFS_E+.adf") as adfs:
        root = adfs._map.object_start(adfs._map.disc_record.root)
    from oaknut.adfs.directory import _calculate_big_dir_check

    block = raw[root : root + 2048]
    dir_size = int.from_bytes(block[0x0C:0x10], "little")
    name_len = int.from_bytes(block[0x08:0x0C], "little")
    num_entries = int.from_bytes(block[0x10:0x14], "little")
    names_size = int.from_bytes(block[0x14:0x18], "little")
    got = _calculate_big_dir_check(block, dir_size, name_len, num_entries, names_size)
    assert got == block[dir_size - 1]


@pytest.mark.parametrize(
    "fmt,nzones,size", [(ADFS_E_PLUS, 1, 819200), (ADFS_F_PLUS, 4, 1638400)]
)
def test_create_blank_plus(fmt, nzones, size):
    adfs = ADFS.create(fmt, title="MadePlus")
    try:
        assert adfs.is_new_map
        assert isinstance(adfs._dir_format, BigDirectoryFormat)
        assert adfs._map.disc_record.format_version == 1
        assert adfs._map.disc_record.nzones == nzones
        assert adfs.total_size == size
        assert list(adfs.root.iterdir()) == []
        assert adfs.validate() == []
    finally:
        adfs.close()


def test_create_blank_e_plus_on_disk(tmp_path):
    image = tmp_path / "eplus.adf"
    with ADFS.create_file(image, ADFS_E_PLUS, title="DiscEPlus") as adfs:
        assert isinstance(adfs._dir_format, BigDirectoryFormat)
    assert image.stat().st_size == 819200
    with ADFS.from_file(image) as adfs:
        assert adfs.is_new_map
        assert isinstance(adfs._dir_format, BigDirectoryFormat)
        assert adfs.validate() == []
        assert list(adfs.root.iterdir()) == []


@pytest.mark.skipif(not (_DIM / "ADFS_E+.adf").exists(), reason="DIM E+ blank not present")
def test_created_e_plus_matches_dim_structurally():
    dim = (_DIM / "ADFS_E+.adf").read_bytes()
    adfs = ADFS.create(ADFS_E_PLUS, title="ADFS\xa0E+")
    try:
        raw = bytes(adfs._disc.sector_range(0, ADFS_E_PLUS.total_sectors))
    finally:
        adfs.close()
    # Bitmap (system fragment + separate root fragment) and root Big directory
    # are byte-identical; only disc id, its zone-check effect and name padding
    # differ (all within the handful of allowed offsets).
    assert raw[0x40:0x400] == dim[0x40:0x400], "bitmap differs"
    assert raw[0x800:0x1000] == dim[0x800:0x1000], "root Big directory differs"


@pytest.mark.skipif(not (_DIM / "ADFS_E+.adf").exists(), reason="DIM E+ blank not present")
def test_big_dir_write_is_refused():
    buffer = memoryview(bytearray((_DIM / "ADFS_E+.adf").read_bytes()))
    adfs = ADFS.from_buffer(buffer)
    try:
        with pytest.raises(ADFSError, match="Big directory"):
            (adfs.root / "Nope").write_bytes(b"x")
    finally:
        adfs.close()

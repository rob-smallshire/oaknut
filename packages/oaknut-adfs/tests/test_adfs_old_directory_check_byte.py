"""The DirCheckByte on old-format (S/M/L) directories.

8-bit ADFS writes zero to the check byte at offset 0x4FF of an old
directory, but RISC OS FileCore writes the PRM's ROR-13 checksum there when
it modifies one, and accepts either. A directory carrying the true
checksum, or zero, must read; any other value marks a broken directory
(issue #87).
"""

from __future__ import annotations

import struct

import pytest
from helpers.adfs_image import make_adfs_s_image, make_old_dir_entry, make_old_directory
from oaknut.adfs.adfs import ADFS
from oaknut.adfs.directory import OldDirectoryFormat
from oaknut.adfs.exceptions import ADFSDirectoryError
from oaknut.discimage.sectors_view import SectorsView

_ROOT_OFFSET = 0x200
_CHECK_BYTE_OFFSET = 0x4FF


def _reference_old_dir_check(block: bytes) -> int:
    """The PRM DirCheckByte over a 1280-byte old directory block.

    Fold, via ``acc = value EOR ROR13(acc)``: the whole words from the start
    of the block to the end of the used entries, then the remaining bytes of
    that region singly, then the tail words from the byte after the
    last-entry mark (&4CC) up to but excluding the word holding the check
    byte (&4FC). The result is the EOR of the four bytes of the accumulator.
    """

    def fold(acc: int, value: int) -> int:
        return value ^ (((acc >> 13) | (acc << 19)) & 0xFFFFFFFF)

    entry_count = 0
    while entry_count < 47 and block[5 + 26 * entry_count] != 0:
        entry_count += 1
    entries_end = 5 + 26 * entry_count

    acc = 0
    whole_words_end = entries_end - entries_end % 4
    for (word,) in struct.iter_unpack("<I", block[:whole_words_end]):
        acc = fold(acc, word)
    for byte in block[whole_words_end:entries_end]:
        acc = fold(acc, byte)
    for (word,) in struct.iter_unpack("<I", block[0x4CC:0x4FC]):
        acc = fold(acc, word)
    return (acc ^ (acc >> 8) ^ (acc >> 16) ^ (acc >> 24)) & 0xFF


def _riscos_style_directory() -> bytearray:
    """An old directory with a few entries and the RISC OS check byte set."""
    entries = [
        make_old_dir_entry("Alpha", load_address=0xFFFFF3E5, length=100, indirect_disc_address=7),
        make_old_dir_entry("Beta", load_address=0xFFFFFF12, length=512, indirect_disc_address=8),
        make_old_dir_entry("T", length=1280, indirect_disc_address=10, is_directory=True),
    ]
    block = make_old_directory(entries, title="RISCOS")
    block[_CHECK_BYTE_OFFSET] = _reference_old_dir_check(block)
    assert block[_CHECK_BYTE_OFFSET] != 0, "choose a block whose checksum is non-zero"
    return block


def _parse(block: bytearray):
    return OldDirectoryFormat().parse(SectorsView([memoryview(block)]), disc_address=2)


def test_zero_check_byte_is_accepted():
    block = make_old_directory([], title="Acorn")
    assert _parse(block).title == "Acorn"


def test_correct_riscos_check_byte_is_accepted():
    directory = _parse(_riscos_style_directory())
    assert [entry.name for entry in directory.entries] == ["Alpha", "Beta", "T"]


def test_correct_check_byte_on_a_full_directory_is_accepted():
    entries = [
        make_old_dir_entry(f"F{i:02d}", length=1, indirect_disc_address=7 + i) for i in range(47)
    ]
    block = make_old_directory(entries)
    block[_CHECK_BYTE_OFFSET] = _reference_old_dir_check(block)
    assert len(_parse(block).entries) == 47


def test_incorrect_non_zero_check_byte_is_rejected():
    block = _riscos_style_directory()
    block[_CHECK_BYTE_OFFSET] ^= 0x01
    with pytest.raises(ADFSDirectoryError, match="check byte"):
        _parse(block)


def test_unused_entry_slots_do_not_contribute_to_the_check_byte():
    block = _riscos_style_directory()
    # Stale bytes after the end-of-entries mark are outside the checksum.
    block[5 + 26 * 3 + 1 : 5 + 26 * 4] = b"\xaa" * 25
    assert len(_parse(block).entries) == 3


def test_riscos_modified_root_lists_through_the_public_api():
    image = make_adfs_s_image(root_title="RISCOS")
    entries = [
        make_old_dir_entry("Text", load_address=0xFFFFFF12, length=0, indirect_disc_address=7)
    ]
    root = make_old_directory(entries, title="RISCOS", parent_address=2)
    root[_CHECK_BYTE_OFFSET] = _reference_old_dir_check(root)
    assert root[_CHECK_BYTE_OFFSET] != 0
    image[_ROOT_OFFSET : _ROOT_OFFSET + 1280] = root

    adfs = ADFS.from_buffer(memoryview(image))
    assert [path.name for path in adfs.root.iterdir()] == ["Text"]

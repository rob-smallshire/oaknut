"""The DirCheckByte on old-format (S/M/L) directories (issue #87).

8-bit ADFS never reads or writes the check byte at offset &4FF of an old
directory: it creates directories with zero there and otherwise writes back
whatever it loaded. RISC OS FileCore writes the PRM's ROR-13 checksum there
when it modifies one. So a RISC OS directory later changed on a BBC keeps a
stale check byte. Old directories therefore read whatever the byte holds;
validate reports a stale one, and repair sets it to the true checksum.

The 8BS Archimedes discs ARC-01 and ARC-03 are real instances: subdirectories
carrying RISC OS checksums, and roots with stale ones.
"""

from __future__ import annotations

import shutil
import struct

import pytest
from helpers.adfs_image import make_adfs_s_image, make_old_dir_entry, make_old_directory
from oaknut.adfs.adfs import ADFS
from oaknut.adfs.directory import OldDirectoryFormat
from oaknut.discimage.sectors_view import SectorsView
from oaknut.filesystem import fix_of

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_ROOT_OFFSET = 0x200
_CHECK_BYTE_OFFSET = 0x4FF

_8BS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-8bs"
#: Each 8BS disc's root: (stored check byte, true checksum).
_STALE_ROOTS = {
    "arc-01.640.adf": (0x9C, 0x30),
    "arc-03.640.adf": (0xA2, 0x79),
}


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


def _view(block: bytearray) -> SectorsView:
    return SectorsView([memoryview(block)])


def _stale_check_byte(block: bytearray) -> tuple[int, int] | None:
    return OldDirectoryFormat().stale_check_byte(_view(block))


def _check_byte_findings(adfs: ADFS) -> list:
    # ARC-03 also has subdirectories lost from the disc; those are not at issue here.
    return [finding for finding in adfs.validate() if "check byte" in str(finding)]


def _parse(block: bytearray):
    return OldDirectoryFormat().parse(_view(block), disc_address=2)


class TestStaleCheckByte:
    def test_zero_is_not_stale(self):
        assert _stale_check_byte(make_old_directory([], title="Acorn")) is None

    def test_the_riscos_checksum_is_not_stale(self):
        assert _stale_check_byte(_riscos_style_directory()) is None

    def test_the_riscos_checksum_on_a_full_directory_is_not_stale(self):
        entries = [
            make_old_dir_entry(f"F{i:02d}", length=1, indirect_disc_address=7 + i)
            for i in range(47)
        ]
        block = make_old_directory(entries)
        block[_CHECK_BYTE_OFFSET] = _reference_old_dir_check(block)
        assert _stale_check_byte(block) is None

    def test_unused_entry_slots_do_not_contribute(self):
        block = _riscos_style_directory()
        # Leftover bytes after the end-of-entries mark are outside the checksum.
        block[5 + 26 * 3 + 1 : 5 + 26 * 4] = b"\xaa" * 25
        assert _stale_check_byte(block) is None

    def test_any_other_value_is_stale(self):
        block = _riscos_style_directory()
        true_check = block[_CHECK_BYTE_OFFSET]
        block[_CHECK_BYTE_OFFSET] ^= 0x01
        assert _stale_check_byte(block) == (true_check ^ 0x01, true_check)


class TestReading:
    def test_a_directory_with_a_stale_check_byte_reads(self):
        block = _riscos_style_directory()
        block[_CHECK_BYTE_OFFSET] ^= 0x01
        assert [entry.name for entry in _parse(block).entries] == ["Alpha", "Beta", "T"]

    def test_a_riscos_modified_root_lists_through_the_public_api(self):
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

    @pytest.mark.parametrize("image_filename", sorted(_STALE_ROOTS))
    def test_8bs_disc_with_a_stale_root_opens(self, image_filename):
        with ADFS.from_file(_8BS_DIRPATH / image_filename, read_only=True) as adfs:
            assert any(path.name.startswith("!") for path in adfs.root.iterdir())


class TestValidateAndRepair:
    @pytest.mark.parametrize("image_filename", sorted(_STALE_ROOTS))
    def test_validate_reports_only_the_stale_root(self, image_filename):
        stored, calculated = _STALE_ROOTS[image_filename]
        # Its subdirectories carry correct RISC OS checksums and pass.
        with ADFS.from_file(_8BS_DIRPATH / image_filename, read_only=True) as adfs:
            (finding,) = _check_byte_findings(adfs)
        message = str(finding)
        assert message.startswith("$: ")
        assert f"&{stored:02X}" in message
        assert f"&{calculated:02X}" in message

    def test_a_stale_check_byte_does_not_stop_traversal(self):
        # Identification asks only whether the tree can be walked.
        with ADFS.from_file(_8BS_DIRPATH / "arc-01.640.adf", read_only=True) as adfs:
            assert adfs._directory_tree_errors() == []

    @pytest.mark.parametrize("image_filename", sorted(_STALE_ROOTS))
    def test_the_fix_sets_only_the_true_checksum(self, image_filename, tmp_path):
        _, calculated = _STALE_ROOTS[image_filename]
        image_filepath = tmp_path / image_filename
        shutil.copyfile(_8BS_DIRPATH / image_filename, image_filepath)
        before = image_filepath.read_bytes()

        with ADFS.from_file(image_filepath) as adfs:
            (finding,) = _check_byte_findings(adfs)
            fix = fix_of(finding)
            assert fix is not None
            assert f"&{calculated:02X}" in fix.description
            fix.apply()

        after = image_filepath.read_bytes()
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        # The root's first track holds &200-&6FF in either layout.
        assert changed == [_ROOT_OFFSET + _CHECK_BYTE_OFFSET]
        assert after[_ROOT_OFFSET + _CHECK_BYTE_OFFSET] == calculated
        with ADFS.from_file(image_filepath, read_only=True) as adfs:
            assert _check_byte_findings(adfs) == []

    def test_a_clean_disc_has_no_check_byte_findings(self):
        image = make_adfs_s_image()
        assert ADFS.from_buffer(memoryview(image)).validate() == []

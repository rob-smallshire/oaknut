"""Tests for files whose block chain spans two member ROMs.

The Electron ROM version of *Mined-Out* is a two-ROM set (image 1 in the
higher socket, image 2 in the lower). ROM 1 holds ``!BOOT``, ``INTRO`` and
``INSTR``, then ``MINED-OUT`` blocks 0-26 with no last-block flag before its
``&2B``; ROM 2 resumes with a full header for ``MINED-OUT`` block 27 and ends
the file at block 31. The ``&2B`` marks the end of a ROM, not the end of a
file. See ``docs/romfs-format-spec.md`` §7 and issue #55.
"""

from __future__ import annotations

import pytest
from oaknut.basic import Verdict, detect
from oaknut.filesystem import Confidence, reader_for
from oaknut.filesystem.exceptions import ReadOnlyFilesystemError
from oaknut.romfs.exceptions import ROMFSError
from oaknut.romfs.filesystem import AcornROMFS
from oaknut.romfs.romfs import ROMFS, ROMFSSet, set_copyright

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"
ROM_1_FILENAME = "Electron_Mined_Out_1.rom"
ROM_2_FILENAME = "Electron_Mined_Out_2.rom"


def _bytes(filename: str) -> bytes:
    return (ROMFS_DIRPATH / filename).read_bytes()


def _mount(filename: str, *, writable: bool = False):
    data = bytearray(_bytes(filename))
    reader = reader_for(data, writable=writable)
    fs = AcornROMFS()
    return fs.open(reader, fs.probe(reader).geometry), data


# -- parsing each member --


def test_leading_member_keeps_its_whole_files():
    rom = ROMFS.from_bytes(_bytes(ROM_1_FILENAME))
    assert [f.name for f in rom.files] == ["!BOOT", "INTRO", "INSTR"]


def test_leading_member_has_a_trailing_fragment():
    rom = ROMFS.from_bytes(_bytes(ROM_1_FILENAME))
    fragment = rom.trailing_fragment
    assert fragment is not None
    assert fragment.name == "MINED-OUT"
    assert fragment.first_block_number == 0
    assert fragment.block_count == 27
    assert len(fragment.data) == 27 * 256
    assert not fragment.ends_file
    assert rom.leading_fragment is None
    assert rom.continues_in_next
    assert not rom.continues_from_previous


def test_continuation_member_has_a_leading_fragment():
    rom = ROMFS.from_bytes(_bytes(ROM_2_FILENAME))
    fragment = rom.leading_fragment
    assert fragment is not None
    assert fragment.name == "MINED-OUT"
    assert fragment.first_block_number == 27
    assert fragment.block_count == 5
    assert fragment.ends_file
    assert fragment.load_address == 0x00FF0E00
    assert fragment.exec_address == 0x00FF8023
    assert rom.files == ()
    assert rom.trailing_fragment is None
    assert rom.continues_from_previous
    assert not rom.continues_in_next


def test_continuation_member_is_complete():
    # ROM 2 ends with its own &2B; what it lacks is a file start, not an end marker.
    assert ROMFS.from_bytes(_bytes(ROM_2_FILENAME)).is_complete


@pytest.mark.parametrize("filename", [ROM_1_FILENAME, ROM_2_FILENAME])
def test_member_round_trips_byte_exact(filename):
    original = _bytes(filename)
    assert ROMFS.from_bytes(original).to_bytes() == original


def test_standalone_rom_has_no_fragments():
    rom = ROMFS.from_bytes(_bytes("Electron_Hopper.rom"))
    assert rom.leading_fragment is None
    assert rom.trailing_fragment is None
    assert not rom.continues_in_next
    assert not rom.continues_from_previous


# -- members are never rewritten --


@pytest.mark.parametrize("filename", [ROM_1_FILENAME, ROM_2_FILENAME])
def test_with_files_refused_on_a_member(filename):
    rom = ROMFS.from_bytes(_bytes(filename))
    with pytest.raises(ROMFSError):
        rom.with_files(rom.files)


def test_copyright_length_change_refused_on_a_member():
    image = _bytes(ROM_1_FILENAME)
    rom = ROMFS.from_bytes(image)
    with pytest.raises(ROMFSError):
        set_copyright(image, rom.copyright + " extra")


@pytest.mark.parametrize("filename", [ROM_1_FILENAME, ROM_2_FILENAME])
def test_mount_refuses_writes_to_a_member(filename):
    mount, data = _mount(filename, writable=True)
    before = bytes(data)
    with pytest.raises(ReadOnlyFilesystemError):
        mount.write_bytes("NEW", b"x")
    assert bytes(data) == before


def test_mount_refuses_removal_from_leading_member():
    mount, data = _mount(ROM_1_FILENAME, writable=True)
    with pytest.raises(ReadOnlyFilesystemError):
        mount.remove("INTRO")


# -- reporting --


def test_leading_member_status_note_names_the_file():
    mount, _ = _mount(ROM_1_FILENAME)
    notes = mount.status_notes()
    assert any("MINED-OUT" in note and "next ROM" in note for note in notes)


def test_continuation_member_status_note_names_the_file():
    mount, _ = _mount(ROM_2_FILENAME)
    notes = mount.status_notes()
    assert any("MINED-OUT" in note and "previous ROM" in note for note in notes)


def test_continuation_member_evidence_does_not_claim_a_missing_end_marker():
    ident = AcornROMFS().probe(reader_for(_bytes(ROM_2_FILENAME)))
    assert ident.confidence == Confidence.STRONG
    assert not any("no end marker" in line for line in ident.evidence)
    assert any("MINED-OUT" in line and "previous ROM" in line for line in ident.evidence)


def test_leading_member_evidence_names_the_continuing_file():
    ident = AcornROMFS().probe(reader_for(_bytes(ROM_1_FILENAME)))
    assert any("MINED-OUT" in line and "next ROM" in line for line in ident.evidence)


# -- joining a set --


def _set() -> ROMFSSet:
    return ROMFSSet.from_images([_bytes(ROM_1_FILENAME), _bytes(ROM_2_FILENAME)])


def test_set_joins_the_spanning_file_in_catalogue_order():
    assert [f.name for f in _set().files] == ["!BOOT", "INTRO", "INSTR", "MINED-OUT"]


def test_joined_file_is_the_whole_program():
    mined_out = {f.name: f for f in _set().files}["MINED-OUT"]
    assert mined_out.length == 32 * 256
    assert mined_out.load_address == 0x00FF0E00
    assert mined_out.exec_address == 0x00FF8023
    assert detect(mined_out.data).verdict is Verdict.BASIC


def test_set_in_the_wrong_order_is_refused():
    with pytest.raises(ROMFSError):
        ROMFSSet.from_images([_bytes(ROM_2_FILENAME), _bytes(ROM_1_FILENAME)])


def test_set_missing_its_continuation_is_refused():
    with pytest.raises(ROMFSError):
        ROMFSSet.from_images([_bytes(ROM_1_FILENAME)])


def test_set_of_standalone_roms_concatenates_their_files():
    hopper = _bytes("Electron_Hopper.rom")
    zalaga = _bytes("Zalaga.rom")
    joined = ROMFSSet.from_images([hopper, zalaga])
    expected = ROMFS.from_bytes(hopper).files + ROMFS.from_bytes(zalaga).files
    assert joined.files == expected

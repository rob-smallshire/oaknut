"""Tests for the ROMFS oaknut.filesystem adapter.

Covers registration, identification through the coordinator, the read
mount, and the write contract: plain ROMFS images are writable; composite
ROMs (with code after the filing system) are read-only.
"""

from __future__ import annotations

import pytest
from oaknut.file import Access, AcornMeta
from oaknut.filesystem import Confidence, filesystem_names, identify, reader_for
from oaknut.filesystem.exceptions import ReadOnlyFilesystemError
from oaknut.romfs.filesystem import AcornROMFS
from oaknut.romfs.romfs import ROMFS

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"


def _bytes(filename: str) -> bytes:
    return (ROMFS_DIRPATH / filename).read_bytes()


def _open_writable(filename: str):
    """A mount over an in-memory writable copy, plus the backing bytearray."""
    data = bytearray(_bytes(filename))
    reader = reader_for(data, writable=True)
    fs = AcornROMFS()
    mount = fs.open(reader, fs.probe(reader).geometry)
    return mount, data


def test_registered():
    assert "acorn-romfs" in filesystem_names()


def test_identify_hopper():
    identifications = identify(_bytes("Electron_Hopper.rom"))
    top = identifications[0]
    assert top.filesystem == "acorn-romfs"
    assert top.confidence == Confidence.STRONG
    assert any("Hopper01" in line for line in top.evidence)


def test_probe_rejects_non_romfs():
    assert AcornROMFS().probe(reader_for(b"\x00" * 16384)) is None


def test_mount_lists_data_files_not_title_block():
    fs = AcornROMFS()
    reader = reader_for(_bytes("Electron_Hopper.rom"))
    mount = fs.open(reader, fs.probe(reader).geometry)
    names = {entry.name for entry in mount.iter_entries("")}
    assert names == {"!BOOT", "HOPPER", "HOPOBJ"}  # *Hopper01* title block excluded
    assert mount.title == "Hopper01"


def test_mount_reads_file_and_metadata():
    fs = AcornROMFS()
    reader = reader_for(_bytes("Electron_Hopper.rom"))
    mount = fs.open(reader, fs.probe(reader).geometry)
    assert mount.exists("HOPOBJ")
    assert len(mount.read_bytes("HOPOBJ")) == 0x2257
    meta = mount.acorn_meta("HOPOBJ")
    assert meta.load_address == 0x3000
    assert meta.exec_address == 0x3000
    assert meta.access & Access.X  # HOPOBJ is *RUN-only (copy-protected)
    assert not meta.access & Access.L  # not the disc delete-lock


def test_zalaga_has_no_title():
    fs = AcornROMFS()
    reader = reader_for(_bytes("Zalaga.rom"))
    mount = fs.open(reader, fs.probe(reader).geometry)
    assert mount.title == ""
    assert {entry.name for entry in mount.iter_entries("")} == {"ZALAGA"}


def test_write_new_file_to_plain_rom():
    mount, data = _open_writable("Electron_Hopper.rom")
    mount.write_bytes("NEWFILE", b"hello world")
    reparsed = ROMFS.from_bytes(bytes(data))
    by_name = {f.name: f for f in reparsed.files}
    assert by_name["NEWFILE"].data == b"hello world"
    # Existing files survive unchanged.
    assert by_name["HOPOBJ"].length == 0x2257


def test_set_metadata_and_rename_round_trip():
    mount, data = _open_writable("Electron_Hopper.rom")
    mount.set_acorn_meta("HOPPER", AcornMeta(load_address=0x1234, exec_address=0x5678, access=0))
    mount.rename("HOPPER", "RENAMED")
    reparsed = ROMFS.from_bytes(bytes(data))
    by_name = {f.name: f for f in reparsed.files}
    assert "HOPPER" not in by_name
    assert by_name["RENAMED"].load_address == 0x1234
    assert by_name["RENAMED"].exec_address == 0x5678


def test_remove_ignores_run_only_protection():
    # The *RUN-only bit is read-protection (copy protection), not a
    # delete-lock — and ROMFS has no delete-lock at all — so removing a
    # run-only file just works, no force needed.
    mount, data = _open_writable("Electron_Hopper.rom")
    assert mount.acorn_meta("HOPOBJ").access & Access.X  # HOPOBJ is run-only
    mount.remove("HOPOBJ")
    assert "HOPOBJ" not in {f.name for f in ROMFS.from_bytes(bytes(data)).files}


def test_run_only_is_a_distinct_axis_from_the_disc_lock():
    # Importing a delete-locked DFS/ADFS file (Access.L) must NOT make the
    # ROMFS file *RUN-only (Access.X) — that would make it unloadable. But a
    # genuine Access.X (a ROMFS→ROMFS copy) is preserved.
    mount, data = _open_writable("Electron_Hopper.rom")

    mount.write_bytes("FROMDFS", b"loader")
    mount.set_acorn_meta("FROMDFS", AcornMeta(load_address=0x1900, exec_address=0x8023,
                                              access=int(Access.L | Access.R | Access.W)))
    mount.write_bytes("FROMROM", b"object")
    mount.set_acorn_meta("FROMROM", AcornMeta(load_address=0x3000, exec_address=0x3000,
                                              access=int(Access.X)))

    by_name = {f.name: f for f in ROMFS.from_bytes(bytes(data)).data_files}
    assert not by_name["FROMDFS"].run_only  # disc lock did NOT make it *RUN-only
    assert by_name["FROMROM"].run_only  # an explicit Access.X is preserved


def test_status_notes_via_capability():
    from oaknut.filesystem import StatusReporting

    fs = AcornROMFS()
    # A plain, complete ROM is writable and has nothing to report.
    reader = reader_for(_bytes("Electron_Hopper.rom"))
    plain = fs.open(reader, fs.probe(reader).geometry)
    assert isinstance(plain, StatusReporting)
    assert plain.status_notes() == ()

    # A composite ROM reports it is read-only.
    creader = reader_for(_bytes("Electron_Countdown_To_Doom_1.rom"))
    composite = fs.open(creader, fs.probe(creader).geometry)
    assert any("read-only" in note for note in composite.status_notes())

    # An incomplete fragment reports it is read-only.
    freader = reader_for(_hopper_fragment())
    fragment = fs.open(freader, fs.probe(freader).geometry)
    assert any("incomplete" in note for note in fragment.status_notes())


def test_mount_treats_slash_name_as_a_flat_filename():
    fs = AcornROMFS()
    reader = reader_for(_bytes("Electron_Tree_Of_Knowledge_1.rom"))
    mount = fs.open(reader, fs.probe(reader).geometry)
    names = {entry.name for entry in mount.iter_entries("")}
    assert "M/C" in names  # the slash is part of the name, not a path
    assert mount.exists("M/C")
    assert len(mount.read_bytes("M/C")) > 0


def test_composite_rom_is_read_only():
    mount, _ = _open_writable("Electron_Countdown_To_Doom_1.rom")
    with pytest.raises(ReadOnlyFilesystemError):
        mount.write_bytes("NEW", b"x")
    # ...but reading still works.
    assert mount.exists("DOOM")
    assert mount.title == "Doom01"


def _hopper_fragment() -> bytes:
    image = _bytes("Electron_Hopper.rom")
    return image[: image.find(b"*HOPOBJ\x00") + 300]


def test_identify_incomplete_fragment():
    fs = AcornROMFS()
    ident = fs.probe(reader_for(_hopper_fragment()))
    assert ident is not None
    assert ident.filesystem == "acorn-romfs"
    assert ident.confidence == Confidence.PROBABLE  # demoted from STRONG
    assert any("incomplete" in line.lower() for line in ident.evidence)


def test_incomplete_fragment_is_read_only():
    data = bytearray(_hopper_fragment())
    reader = reader_for(data, writable=True)
    fs = AcornROMFS()
    mount = fs.open(reader, fs.probe(reader).geometry)
    # Reading the complete files works...
    assert mount.exists("HOPPER")
    assert len(mount.read_bytes("HOPPER")) == 0x3D5
    # ...but every mutation is refused, since the ROM is part of a larger whole.
    with pytest.raises(ReadOnlyFilesystemError):
        mount.write_bytes("NEW", b"x")
    with pytest.raises(ReadOnlyFilesystemError):
        mount.remove("HOPPER")

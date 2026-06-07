"""Writing/renaming in a ROMFS must not produce two files of one name.

ROMFS is a flat CFS block stream looked up by name, so two files sharing
a name leaves one unreachable. Writing an existing name overwrites it,
renaming onto an existing name is refused, and ``_commit`` asserts the
no-duplicate-names post-condition over the rebuilt file list.
"""

import pytest
from oaknut.filesystem import reader_for
from oaknut.romfs.exceptions import ROMFSError
from oaknut.romfs.filesystem import AcornROMFS
from oaknut.romfs.romfs import ROMFS, ROMFSFile, build_rom_image


def _writable_mount():
    data = bytearray(build_rom_image(title="DISC", size=16384))
    reader = reader_for(data, writable=True)
    fs = AcornROMFS()
    mount = fs.open(reader, fs.probe(reader).geometry)
    return mount, data


def _names(data):
    return [f.name for f in ROMFS.from_bytes(bytes(data)).data_files]


class TestRomfsWriteOverwrites:
    def test_rewriting_a_file_overwrites_not_duplicates(self):
        mount, data = _writable_mount()
        mount.write_bytes("README", b"first")
        mount.write_bytes("README", b"second")
        assert _names(data) == ["README"]
        assert mount.read_bytes("README") == b"second"


class TestRomfsRenameGuard:
    def test_rename_onto_existing_name_is_refused(self):
        mount, _ = _writable_mount()
        mount.write_bytes("AAA", b"a")
        mount.write_bytes("BBB", b"b")
        with pytest.raises(ROMFSError):
            mount.rename("AAA", "BBB")

    def test_refused_rename_leaves_one_of_each(self):
        mount, data = _writable_mount()
        mount.write_bytes("AAA", b"a")
        mount.write_bytes("BBB", b"b")
        with pytest.raises(ROMFSError):
            mount.rename("AAA", "BBB")
        assert sorted(_names(data)) == ["AAA", "BBB"]


class TestRomfsCommitPostCondition:
    def test_commit_rejects_a_duplicate_file_list(self):
        # The backstop: handing _commit a file list that already contains a
        # duplicate name must fail loudly rather than write corruption.
        mount, _ = _writable_mount()
        dup = (
            ROMFSFile("SAME", 0, 0, False, b"one"),
            ROMFSFile("SAME", 0, 0, False, b"two"),
        )
        with pytest.raises(AssertionError, match="duplicate entries"):
            mount._commit(dup)

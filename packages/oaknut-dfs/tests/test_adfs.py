"""Tests for ADFS support — directory parsing, free space map, and public API.

These tests construct ADFS disc images in memory with known content,
then verify parsing through the public ADFSPath API.
"""

import pytest

from helpers.adfs_image import (
    make_adfs_s_image as _make_adfs_s_image,
    make_old_dir_entry as _make_old_dir_entry,
    make_old_directory as _make_old_directory,
    make_old_free_space_map as _make_old_free_space_map,
)
from oaknut_dfs.adfs import ADFS, ADFSPath, ADFSStat
from oaknut_dfs.adfs_directory import OldDirectoryFormat
from oaknut_dfs.adfs_free_space_map import OldFreeSpaceMap, _calculate_old_map_checksum
from oaknut_dfs.exceptions import ADFSDirectoryError, ADFSMapError, ADFSPathError
from oaknut_dfs.sectors_view import SectorsView


# --- Free Space Map Tests ---


class TestOldFreeSpaceMapChecksum:

    def test_checksum_of_zeros(self):
        """Checksum of 256 zero bytes should be 0."""
        buf = bytearray(512)
        view = SectorsView([memoryview(buf)])
        assert _calculate_old_map_checksum(view, 0) == 0

    def test_checksum_round_trip(self):
        """A map built with _make_old_free_space_map should validate."""
        fsm_bytes = _make_old_free_space_map([(7, 633)], disc_size_sectors=640)
        view = SectorsView([memoryview(fsm_bytes)])
        fsm = OldFreeSpaceMap(view)
        assert fsm.validate() == []


class TestOldFreeSpaceMap:

    def setup_method(self):
        self.fsm_bytes = _make_old_free_space_map(
            [(7, 633)],
            disc_size_sectors=640,
            boot_option=2,
            disc_id=0x1234,
        )
        view = SectorsView([memoryview(self.fsm_bytes)])
        self.fsm = OldFreeSpaceMap(view)

    def test_num_entries(self):
        assert self.fsm.num_entries == 1

    def test_free_space_entries(self):
        entries = self.fsm.free_space_entries()
        assert len(entries) == 1
        assert entries[0] == (7 * 256, 633 * 256)

    def test_free_space(self):
        assert self.fsm.free_space == 633 * 256

    def test_total_size(self):
        assert self.fsm.total_size == 640 * 256

    def test_total_sectors(self):
        assert self.fsm.total_sectors == 640

    def test_boot_option(self):
        assert self.fsm.boot_option == 2

    def test_disc_id(self):
        assert self.fsm.disc_id == 0x1234

    def test_validate_clean(self):
        assert self.fsm.validate() == []

    def test_bad_checksum_raises(self):
        self.fsm_bytes[0x0FF] ^= 0xFF  # Corrupt sector 0 checksum
        view = SectorsView([memoryview(self.fsm_bytes)])
        with pytest.raises(ADFSMapError, match="checksum"):
            OldFreeSpaceMap(view)

    def test_multiple_free_entries(self):
        fsm_bytes = _make_old_free_space_map(
            [(7, 100), (200, 50), (300, 340)],
            disc_size_sectors=640,
        )
        view = SectorsView([memoryview(fsm_bytes)])
        fsm = OldFreeSpaceMap(view)
        assert fsm.num_entries == 3
        entries = fsm.free_space_entries()
        assert entries[0] == (7 * 256, 100 * 256)
        assert entries[1] == (200 * 256, 50 * 256)
        assert entries[2] == (300 * 256, 340 * 256)


# --- Directory Parsing Tests ---


class TestOldDirectoryFormat:

    def test_parse_empty_directory(self):
        fmt = OldDirectoryFormat()
        dir_bytes = _make_old_directory([], dir_name="$", title="TestDisc")
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x200)

        assert directory.name == "$"
        assert directory.title == "TestDisc"
        assert directory.entries == ()
        assert directory.disc_address == 0x200

    def test_parse_directory_with_files(self):
        fmt = OldDirectoryFormat()
        entries = [
            _make_old_dir_entry("Hello", load_address=0x1900, length=256,
                                indirect_disc_address=7),
            _make_old_dir_entry("World", load_address=0x2000, length=512,
                                indirect_disc_address=9),
        ]
        dir_bytes = _make_old_directory(entries, title="MyDisc")
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x200)

        assert len(directory.entries) == 2
        assert directory.entries[0].name == "Hello"
        assert directory.entries[0].load_address == 0x1900
        assert directory.entries[0].length == 256
        assert directory.entries[0].indirect_disc_address == 7
        assert directory.entries[1].name == "World"

    def test_parse_directory_with_subdirectory(self):
        fmt = OldDirectoryFormat()
        entries = [
            _make_old_dir_entry("Games", length=1280,
                                indirect_disc_address=32,
                                is_directory=True),
        ]
        dir_bytes = _make_old_directory(entries)
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x200)

        assert directory.entries[0].is_directory is True

    def test_attributes_parsed(self):
        fmt = OldDirectoryFormat()
        entries = [
            _make_old_dir_entry("Locked", locked=True, owner_read=True,
                                owner_write=False),
        ]
        dir_bytes = _make_old_directory(entries)
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x200)

        entry = directory.entries[0]
        assert entry.attributes.locked is True
        assert entry.attributes.owner_read is True
        assert entry.attributes.owner_write is False

    def test_bad_signature_raises(self):
        fmt = OldDirectoryFormat()
        dir_bytes = _make_old_directory([])
        dir_bytes[1:5] = b"XXXX"  # Corrupt signature
        view = SectorsView([memoryview(dir_bytes)])
        with pytest.raises(ADFSDirectoryError, match="signature"):
            fmt.parse(view, 0x200)

    def test_mismatched_sequence_raises(self):
        fmt = OldDirectoryFormat()
        dir_bytes = _make_old_directory([], sequence_number=1)
        # Corrupt EndMasSeq
        dir_bytes[0x4CB + 47] = 99
        view = SectorsView([memoryview(dir_bytes)])
        with pytest.raises(ADFSDirectoryError, match="Broken directory"):
            fmt.parse(view, 0x200)

    def test_nonzero_check_byte_raises(self):
        fmt = OldDirectoryFormat()
        dir_bytes = _make_old_directory([])
        # Set the reserved check byte to a non-zero value
        dir_bytes[0x4CB + 52] = 0x42
        view = SectorsView([memoryview(dir_bytes)])
        with pytest.raises(ADFSDirectoryError, match="Reserved check byte"):
            fmt.parse(view, 0x200)

    def test_find_case_insensitive(self):
        fmt = OldDirectoryFormat()
        entries = [
            _make_old_dir_entry("Hello"),
        ]
        dir_bytes = _make_old_directory(entries)
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x200)

        assert directory.find("Hello") is not None
        assert directory.find("hello") is not None
        assert directory.find("HELLO") is not None
        assert directory.find("Missing") is None

    def test_format_properties(self):
        fmt = OldDirectoryFormat()
        assert fmt.size_in_bytes == 1280
        assert fmt.size_in_sectors == 5
        assert fmt.max_entries == 47

    def test_parent_address(self):
        fmt = OldDirectoryFormat()
        dir_bytes = _make_old_directory([], parent_address=0x200)
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x700)

        assert directory.parent_address == 0x200

    def test_nick_signature(self):
        """The 'Nick' signature should also be accepted."""
        fmt = OldDirectoryFormat()
        dir_bytes = _make_old_directory([], signature=b"Nick")
        view = SectorsView([memoryview(dir_bytes)])
        directory = fmt.parse(view, 0x200)
        assert directory.name == "$"


# --- ADFS Public API Tests ---


class TestADFSFromBuffer:

    def test_open_empty_adfs_s(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.title == "TestDisc"
        assert adfs.total_size == 640 * 256

    def test_root_is_directory(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.root.is_dir()
        assert not adfs.root.is_file()
        assert adfs.root.exists()

    def test_root_name(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.root.name == "$"
        assert adfs.root.path == "$"

    def test_empty_root_iterdir(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        entries = list(adfs.root)
        assert entries == []

    def test_repr(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        r = repr(adfs)
        assert "ADFS" in r


class TestADFSWithFiles:

    def setup_method(self):
        # Create a disc with two files
        file1_data = b"Hello, ADFS World!" + b"\x00" * (256 - 18)
        file2_data = b"Second file" + b"\x00" * (512 - 11)

        entries = [
            _make_old_dir_entry("FileOne", load_address=0x1900,
                                exec_address=0x1900, length=18,
                                indirect_disc_address=7),
            _make_old_dir_entry("FileTwo", load_address=0x2000,
                                exec_address=0x2000, length=11,
                                indirect_disc_address=8),
        ]
        buf = _make_adfs_s_image(
            root_entries=entries,
            free_entries=[(10, 630)],
            file_data={7: file1_data, 8: file2_data},
        )
        self.adfs = ADFS.from_buffer(memoryview(buf))

    def test_iterdir_returns_paths(self):
        entries = list(self.adfs.root)
        assert len(entries) == 2
        assert all(isinstance(e, ADFSPath) for e in entries)

    def test_iterdir_names(self):
        names = [e.name for e in self.adfs.root]
        assert names == ["FileOne", "FileTwo"]

    def test_path_navigation(self):
        file1 = self.adfs.root / "FileOne"
        assert file1.path == "$.FileOne"
        assert file1.name == "FileOne"

    def test_exists(self):
        assert (self.adfs.root / "FileOne").exists()
        assert not (self.adfs.root / "Missing").exists()

    def test_is_file(self):
        assert (self.adfs.root / "FileOne").is_file()
        assert not (self.adfs.root / "FileOne").is_dir()

    def test_read_bytes(self):
        data = (self.adfs.root / "FileOne").read_bytes()
        assert data == b"Hello, ADFS World!"

    def test_read_second_file(self):
        data = (self.adfs.root / "FileTwo").read_bytes()
        assert data == b"Second file"

    def test_stat(self):
        stat = (self.adfs.root / "FileOne").stat()
        assert isinstance(stat, ADFSStat)
        assert stat.length == 18
        assert stat.load_address == 0x1900
        assert stat.is_directory is False
        assert stat.owner_read is True
        assert stat.locked is False

    def test_contains(self):
        assert "FileOne" in self.adfs.root
        assert "Missing" not in self.adfs.root

    def test_read_nonexistent_raises(self):
        with pytest.raises(ADFSPathError):
            (self.adfs.root / "Missing").read_bytes()

    def test_read_directory_as_file_raises(self):
        with pytest.raises(ADFSPathError, match="root directory"):
            self.adfs.root.read_bytes()

    def test_path_factory(self):
        p = self.adfs.path("$.FileOne")
        assert p.exists()
        assert p.read_bytes() == b"Hello, ADFS World!"


class TestADFSWithSubdirectory:

    def setup_method(self):
        # Create a disc with a subdirectory containing a file
        file_data = b"Inside subdir" + b"\x00" * (256 - 13)

        # Subdirectory at sector 7 (5 sectors = 7-11)
        subdir_entry = _make_old_dir_entry(
            "Games", length=1280,
            indirect_disc_address=7,
            is_directory=True,
        )

        # File inside subdir at sector 12
        file_entry = _make_old_dir_entry(
            "Elite", load_address=0x3000, length=13,
            indirect_disc_address=12,
        )

        # Build subdirectory
        subdir_bytes = _make_old_directory(
            [file_entry],
            dir_name="Games",
            title="Games Directory",
            parent_address=0x200,  # Parent is root
        )

        # Build root
        buf = _make_adfs_s_image(
            root_entries=[subdir_entry],
            free_entries=[(13, 627)],
        )

        # Write subdirectory
        buf[7 * 256:7 * 256 + 1280] = subdir_bytes
        # Write file data
        buf[12 * 256:12 * 256 + 256] = file_data

        self.adfs = ADFS.from_buffer(memoryview(buf))

    def test_subdir_exists(self):
        assert (self.adfs.root / "Games").exists()
        assert (self.adfs.root / "Games").is_dir()

    def test_navigate_into_subdir(self):
        games = self.adfs.root / "Games"
        entries = list(games)
        assert len(entries) == 1
        assert entries[0].name == "Elite"

    def test_read_file_in_subdir(self):
        data = (self.adfs.root / "Games" / "Elite").read_bytes()
        assert data == b"Inside subdir"

    def test_deep_path(self):
        elite = self.adfs.root / "Games" / "Elite"
        assert elite.path == "$.Games.Elite"
        assert elite.parts == ("$", "Games", "Elite")

    def test_parent(self):
        elite = self.adfs.root / "Games" / "Elite"
        assert elite.parent.path == "$.Games"
        assert elite.parent.parent.path == "$"

    def test_root_parent_is_self(self):
        assert self.adfs.root.parent.path == "$"

    def test_walk(self):
        results = list(self.adfs.root.walk())
        assert len(results) == 2  # root + Games

        root_path, root_dirs, root_files = results[0]
        assert str(root_path) == "$"
        assert root_dirs == ["Games"]
        assert root_files == []

        games_path, games_dirs, games_files = results[1]
        assert str(games_path) == "$.Games"
        assert games_dirs == []
        assert games_files == ["Elite"]

    def test_stat_on_subdir(self):
        stat = (self.adfs.root / "Games").stat()
        assert stat.is_directory is True

    def test_nonexistent_intermediate_raises(self):
        with pytest.raises(ADFSPathError, match="not found"):
            (self.adfs.root / "Missing" / "File").read_bytes()


class TestADFSPathEquality:

    def test_equal_paths(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        p1 = adfs.root / "Games"
        p2 = adfs.root / "Games"
        assert p1 == p2

    def test_case_insensitive_equality(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        p1 = adfs.root / "Games"
        p2 = adfs.root / "games"
        assert p1 == p2

    def test_hash_case_insensitive(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        p1 = adfs.root / "Games"
        p2 = adfs.root / "games"
        assert hash(p1) == hash(p2)

    def test_repr(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        p = adfs.root / "Games"
        assert repr(p) == "ADFSPath('$.Games')"


class TestADFSFormatDetection:

    def test_wrong_size_raises(self):
        buf = bytearray(1000)
        with pytest.raises(Exception):
            ADFS.from_buffer(memoryview(buf))

    def test_bad_directory_signature_raises(self):
        buf = _make_adfs_s_image()
        # Corrupt root directory signature
        buf[0x201:0x205] = b"XXXX"
        # Also need to make the map still valid
        with pytest.raises(Exception):
            ADFS.from_buffer(memoryview(buf))


class TestADFSDiscMetadata:

    def test_boot_option(self):
        fsm_bytes = _make_old_free_space_map([(7, 633)], boot_option=3)
        entries = [_make_old_dir_entry("File", length=10, indirect_disc_address=7*256)]
        buf = _make_adfs_s_image(root_entries=entries)
        # Overwrite FSM with our custom one
        buf[0:512] = fsm_bytes
        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.boot_option == 3

    def test_free_space(self):
        buf = _make_adfs_s_image(free_entries=[(7, 100)])
        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.free_space == 100 * 256

    def test_validate_clean(self):
        buf = _make_adfs_s_image()
        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.validate() == []

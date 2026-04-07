"""Tests for ADFS support — directory parsing, free space map, and public API.

These tests construct ADFS disc images in memory with known content,
then verify parsing through the public ADFSPath API.
"""

import struct

import pytest

from oaknut_dfs.adfs import ADFS, ADFSPath, ADFSStat
from oaknut_dfs.adfs_directory import OldDirectoryFormat
from oaknut_dfs.adfs_free_space_map import OldFreeSpaceMap, _calculate_old_map_checksum
from oaknut_dfs.exceptions import ADFSDirectoryError, ADFSMapError, ADFSPathError
from oaknut_dfs.sectors_view import SectorsView


# --- Helpers for constructing ADFS disc images ---


def _write_24bit_le(buf: bytearray, offset: int, value: int) -> None:
    """Write a 24-bit little-endian value."""
    buf[offset] = value & 0xFF
    buf[offset + 1] = (value >> 8) & 0xFF
    buf[offset + 2] = (value >> 16) & 0xFF


def _make_old_dir_entry(
    name: str,
    load_address: int = 0,
    exec_address: int = 0,
    length: int = 0,
    indirect_disc_address: int = 0,
    sequence_number: int = 0,
    owner_read: bool = True,
    owner_write: bool = True,
    locked: bool = False,
    is_directory: bool = False,
) -> bytes:
    """Build a 26-byte old-format directory entry."""
    entry = bytearray(26)

    # Encode name (up to 10 chars, space-padded)
    name_bytes = name.encode("ascii").ljust(10, b"\r")

    # Set attribute bits in top bit of each name character
    attrs = [
        owner_read, owner_write, locked, is_directory,
        False,  # execute
        True,   # public read
        False,  # public write
        False,  # public execute
        False,  # private
        False,  # unused
    ]
    for i in range(10):
        entry[i] = name_bytes[i] | (0x80 if attrs[i] else 0x00)

    # Load, exec, length (little-endian 32-bit)
    struct.pack_into("<I", entry, 0x0A, load_address)
    struct.pack_into("<I", entry, 0x0E, exec_address)
    struct.pack_into("<I", entry, 0x12, length)

    # Indirect disc address (24-bit LE)
    _write_24bit_le(entry, 0x16, indirect_disc_address)
    entry[0x19] = sequence_number

    return bytes(entry)


def _make_old_directory(
    entries: list[bytes],
    dir_name: str = "$",
    title: str = "",
    parent_address: int = 0,
    signature: bytes = b"Hugo",
    sequence_number: int = 0,
) -> bytearray:
    """Build a 1280-byte old-format directory block."""
    buf = bytearray(1280)

    # Header
    buf[0x00] = sequence_number
    buf[0x01:0x05] = signature

    # Entries (26 bytes each, starting at offset 0x05)
    for i, entry_bytes in enumerate(entries):
        offset = 0x05 + i * 26
        buf[offset:offset + 26] = entry_bytes

    # End-of-entries marker (first byte of next entry slot = 0)
    if len(entries) < 47:
        next_offset = 0x05 + len(entries) * 26
        buf[next_offset] = 0x00

    # Tail (starts at offset 0x4CB)
    tail = 0x4CB
    buf[tail] = 0x00  # OldDirLastMark

    # Directory name (10 bytes, padded with CR)
    dir_name_bytes = dir_name.encode("ascii").ljust(10, b"\r")
    buf[tail + 1:tail + 11] = dir_name_bytes

    # Parent address (3 bytes LE)
    _write_24bit_le(buf, tail + 11, parent_address)

    # Title (19 bytes, padded with CR)
    title_bytes = title.encode("ascii").ljust(19, b"\r")
    buf[tail + 14:tail + 33] = title_bytes

    # Reserved (14 bytes, must be zero) — already zero

    # EndMasSeq
    buf[tail + 47] = sequence_number
    # EndName
    buf[tail + 48:tail + 52] = signature

    # Check byte is reserved (must be zero) on old-format directories
    buf[tail + 52] = 0x00

    return buf


def _make_old_free_space_map(
    free_entries: list[tuple[int, int]],
    disc_size_sectors: int = 640,
    boot_option: int = 0,
    disc_id: int = 0,
) -> bytearray:
    """Build a 512-byte old-format free space map (sectors 0-1).

    Args:
        free_entries: List of (start_sector, length_sectors) pairs.
        disc_size_sectors: Total disc size in sectors.
        boot_option: Boot option (0-3).
        disc_id: Disc identifier.
    """
    buf = bytearray(512)

    # Write free space entries
    for i, (start, length) in enumerate(free_entries):
        _write_24bit_le(buf, 0x000 + i * 3, start)
        _write_24bit_le(buf, 0x100 + i * 3, length)

    # Disc size (3 bytes LE at 0x0FC)
    _write_24bit_le(buf, 0x0FC, disc_size_sectors)

    # Disc ID (2 bytes LE at 0x1FB)
    buf[0x1FB] = disc_id & 0xFF
    buf[0x1FC] = (disc_id >> 8) & 0xFF

    # Boot option at 0x1FD
    buf[0x1FD] = boot_option

    # FreeEnd pointer at 0x1FE
    buf[0x1FE] = len(free_entries) * 3

    # Calculate and set checksums
    view = SectorsView([memoryview(buf)])
    buf[0x0FF] = _calculate_old_map_checksum(view, 0x000)
    buf[0x1FF] = _calculate_old_map_checksum(view, 0x100)

    return buf


def _make_adfs_s_image(
    root_entries: list[bytes] | None = None,
    root_title: str = "TestDisc",
    free_entries: list[tuple[int, int]] | None = None,
    file_data: dict[int, bytes] | None = None,
) -> bytearray:
    """Build a complete ADFS S disc image (160KB, single-sided, 40 tracks).

    Args:
        root_entries: Directory entries for root. Default: empty.
        root_title: Root directory title.
        free_entries: Free space map entries. Default: all space after root dir is free.
        file_data: Dict mapping sector number to file data bytes.
    """
    disc_size_sectors = 640  # 40 tracks × 16 sectors
    buf = bytearray(disc_size_sectors * 256)  # 163840 bytes

    # Build free space map (sectors 0-1)
    if free_entries is None:
        # Root dir occupies sectors 2-6; rest is free
        free_entries = [(7, disc_size_sectors - 7)]

    fsm = _make_old_free_space_map(
        free_entries, disc_size_sectors=disc_size_sectors
    )
    buf[0:512] = fsm

    # Build root directory (sectors 2-6, offset 0x200)
    if root_entries is None:
        root_entries = []

    root_dir = _make_old_directory(
        root_entries, dir_name="$", title=root_title, parent_address=0x200
    )
    buf[0x200:0x200 + 1280] = root_dir

    # Write file data
    if file_data:
        for sector, data in file_data.items():
            offset = sector * 256
            buf[offset:offset + len(data)] = data

    return buf


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

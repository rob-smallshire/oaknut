"""Helpers for constructing ADFS disc images in memory for testing."""

import struct

from oaknut_dfs.adfs_free_space_map import _calculate_old_map_checksum
from oaknut_dfs.sectors_view import SectorsView


def write_24bit_le(buf: bytearray, offset: int, value: int) -> None:
    """Write a 24-bit little-endian value."""
    buf[offset] = value & 0xFF
    buf[offset + 1] = (value >> 8) & 0xFF
    buf[offset + 2] = (value >> 16) & 0xFF


def make_old_dir_entry(
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
    write_24bit_le(entry, 0x16, indirect_disc_address)
    entry[0x19] = sequence_number

    return bytes(entry)


def make_old_directory(
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
    write_24bit_le(buf, tail + 11, parent_address)

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


def make_old_free_space_map(
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
        write_24bit_le(buf, 0x000 + i * 3, start)
        write_24bit_le(buf, 0x100 + i * 3, length)

    # Disc size (3 bytes LE at 0x0FC)
    write_24bit_le(buf, 0x0FC, disc_size_sectors)

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


def make_adfs_s_image(
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

    fsm = make_old_free_space_map(
        free_entries, disc_size_sectors=disc_size_sectors
    )
    buf[0:512] = fsm

    # Build root directory (sectors 2-6, offset 0x200)
    if root_entries is None:
        root_entries = []

    root_dir = make_old_directory(
        root_entries, dir_name="$", title=root_title, parent_address=0x200
    )
    buf[0x200:0x200 + 1280] = root_dir

    # Write file data
    if file_data:
        for sector, data in file_data.items():
            offset = sector * 256
            buf[offset:offset + len(data)] = data

    return buf

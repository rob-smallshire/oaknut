"""ADFS free space map parsing — internal module.

Parses the old-format free space map (ADFS S/M/L/D) from sectors 0–1.
"""

from __future__ import annotations

from oaknut_dfs.exceptions import ADFSDiscFullError, ADFSMapError
from oaknut_dfs.sectors_view import SectorsView


# Old map layout constants
_MAX_FREE_ENTRIES = 82
_BYTES_PER_ENTRY = 3

# Sector 0 offsets
_FREE_START_OFFSET = 0x000      # 82 × 3-byte start addresses
_RESERVED_OFFSET = 0x0F6        # 1 byte, must be zero
_OLD_NAME_0_OFFSET = 0x0F7      # 5 bytes (chars 1, 3, 5, 7, 9 of disc name)
_OLD_SIZE_OFFSET = 0x0FC        # 3 bytes, disc size in sectors
_CHECK_0_OFFSET = 0x0FF         # 1 byte, checksum

# Sector 1 offsets
_FREE_LEN_OFFSET = 0x100        # 82 × 3-byte lengths
_OLD_NAME_1_OFFSET = 0x1F6      # 5 bytes (chars 0, 2, 4, 6, 8 of disc name)
_OLD_ID_OFFSET = 0x1FB          # 2 bytes, disc identifier
_OLD_BOOT_OFFSET = 0x1FD        # 1 byte, boot option
_FREE_END_OFFSET = 0x1FE        # 1 byte, pointer to end of free space list
_CHECK_1_OFFSET = 0x1FF         # 1 byte, checksum


def _read_24bit_le(data: SectorsView, offset: int) -> int:
    """Read a 24-bit little-endian value."""
    return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)


def _write_24bit_le(data: SectorsView, offset: int, value: int) -> None:
    """Write a 24-bit little-endian value."""
    data[offset] = value & 0xFF
    data[offset + 1] = (value >> 8) & 0xFF
    data[offset + 2] = (value >> 16) & 0xFF


def _calculate_old_map_checksum(data: SectorsView, start: int) -> int:
    """Calculate the old map checksum for a 256-byte block.

    Add bytes from offset 0xFE down to 0x00 (relative to start), with
    carry propagation. The checksum byte itself (at start + 0xFF) is
    substituted with zero during calculation.

    The carry is reset to zero before adding each byte. If the running
    total exceeds 0xFF, carry is set to 1 and the total is truncated
    to 8 bits. The carry is then added when processing the next byte.
    """
    total = 0
    carry = 0
    # Process from 0xFE down to 0x00
    for offset in range(0xFE, -1, -1):
        byte_val = data[start + offset]
        total = total + byte_val + carry
        if total > 0xFF:
            carry = 1
            total &= 0xFF
        else:
            carry = 0
    return total & 0xFF


class OldFreeSpaceMap:
    """Old ADFS free space map (sectors 0–1, 512 bytes).

    Sector 0: free space start addresses (82 × 3 bytes) + metadata + checksum.
    Sector 1: free space lengths (82 × 3 bytes) + metadata + checksum.
    """

    def __init__(self, data: SectorsView, *, verify_checksums: bool = True):
        """Parse old free space map from sector data.

        Args:
            data: SectorsView covering sectors 0 and 1 (512 bytes).
            verify_checksums: If True, verify map checksums on construction.

        Raises:
            ADFSMapError: If checksums are invalid or data is malformed.
        """
        if len(data) < 512:
            raise ADFSMapError(
                f"Free space map data too short: {len(data)} bytes, need 512"
            )

        self._data = data

        if verify_checksums:
            errors = self._check_checksums()
            if errors:
                raise ADFSMapError("; ".join(errors))

    def _check_checksums(self) -> list[str]:
        """Verify map checksums only. Used during construction."""
        errors = []

        expected_0 = self._data[_CHECK_0_OFFSET]
        calculated_0 = _calculate_old_map_checksum(self._data, 0x000)
        if expected_0 != calculated_0:
            errors.append(
                f"Sector 0 checksum mismatch: expected 0x{expected_0:02X}, "
                f"calculated 0x{calculated_0:02X}"
            )

        expected_1 = self._data[_CHECK_1_OFFSET]
        calculated_1 = _calculate_old_map_checksum(self._data, 0x100)
        if expected_1 != calculated_1:
            errors.append(
                f"Sector 1 checksum mismatch: expected 0x{expected_1:02X}, "
                f"calculated 0x{calculated_1:02X}"
            )

        return errors

    def validate(self) -> list[str]:
        """Validate the free space map. Returns list of error messages."""
        errors = self._check_checksums()

        # Check FreeEnd is a multiple of 3
        free_end = self._data[_FREE_END_OFFSET]
        if free_end % 3 != 0:
            errors.append(
                f"FreeEnd pointer ({free_end}) is not a multiple of 3"
            )

        # Check FreeEnd doesn't exceed maximum
        if free_end > _MAX_FREE_ENTRIES * _BYTES_PER_ENTRY:
            errors.append(
                f"FreeEnd pointer ({free_end}) exceeds maximum "
                f"({_MAX_FREE_ENTRIES * _BYTES_PER_ENTRY})"
            )

        return errors

    @property
    def num_entries(self) -> int:
        """Number of free space entries."""
        free_end = self._data[_FREE_END_OFFSET]
        return free_end // _BYTES_PER_ENTRY

    def free_space_entries(self) -> list[tuple[int, int]]:
        """Return list of (start_address, length) pairs for free space regions.

        Addresses and lengths are in bytes (sector address × 256).
        """
        entries = []
        for i in range(self.num_entries):
            offset = i * _BYTES_PER_ENTRY
            start_sector = _read_24bit_le(self._data, _FREE_START_OFFSET + offset)
            length_sectors = _read_24bit_le(self._data, _FREE_LEN_OFFSET + offset)
            entries.append((start_sector * 256, length_sectors * 256))
        return entries

    @property
    def free_space(self) -> int:
        """Total free space in bytes."""
        return sum(length for _, length in self.free_space_entries())

    @property
    def total_size(self) -> int:
        """Total disc size in bytes."""
        size_sectors = _read_24bit_le(self._data, _OLD_SIZE_OFFSET)
        return size_sectors * 256

    @property
    def total_sectors(self) -> int:
        """Total disc size in sectors."""
        return _read_24bit_le(self._data, _OLD_SIZE_OFFSET)

    @property
    def disc_name(self) -> str:
        """Disc name, interleaved across sectors 0 and 1.

        OldName0 (at 0x0F7): chars at positions 1, 3, 5, 7, 9
        OldName1 (at 0x1F6): chars at positions 0, 2, 4, 6, 8

        Note: S, M and L format discs on BBC/Electron don't use
        the disc name fields, so this may return empty or garbage.
        """
        name_chars = [0] * 10
        for i in range(5):
            name_chars[i * 2] = self._data[_OLD_NAME_1_OFFSET + i]
            name_chars[i * 2 + 1] = self._data[_OLD_NAME_0_OFFSET + i]
        return bytes(name_chars).rstrip(b"\x00 ").decode("ascii", errors="replace")

    @property
    def disc_id(self) -> int:
        """Disc identifier (2 bytes, little-endian)."""
        return self._data[_OLD_ID_OFFSET] | (self._data[_OLD_ID_OFFSET + 1] << 8)

    @property
    def boot_option(self) -> int:
        """Boot option (0–3)."""
        return self._data[_OLD_BOOT_OFFSET]

    def set_boot_option(self, value: int) -> None:
        """Set boot option and recalculate checksums."""
        self._data[_OLD_BOOT_OFFSET] = value & 0xFF
        self._recalculate_checksums()

    # --- Mutation ---

    def allocate(self, num_sectors: int) -> int:
        """Allocate contiguous sectors using first-fit.

        Args:
            num_sectors: Number of sectors to allocate.

        Returns:
            Start sector of the allocated region.

        Raises:
            ValueError: If num_sectors is not positive.
            ADFSMapError: If no free region is large enough.
        """
        if num_sectors <= 0:
            raise ValueError(f"num_sectors must be positive, got {num_sectors}")

        n = self.num_entries
        for i in range(n):
            offset = i * _BYTES_PER_ENTRY
            start = _read_24bit_le(self._data, _FREE_START_OFFSET + offset)
            length = _read_24bit_le(self._data, _FREE_LEN_OFFSET + offset)

            if length >= num_sectors:
                if length == num_sectors:
                    # Exact fit — remove this entry by shifting subsequent ones down
                    self._remove_entry(i, n)
                else:
                    # Partial fit — shrink this entry
                    new_start = start + num_sectors
                    new_length = length - num_sectors
                    _write_24bit_le(self._data, _FREE_START_OFFSET + offset, new_start)
                    _write_24bit_le(self._data, _FREE_LEN_OFFSET + offset, new_length)

                self._recalculate_checksums()
                return start

        raise ADFSDiscFullError(
            f"No free space region large enough for {num_sectors} sectors"
        )

    def free(self, start_sector: int, num_sectors: int) -> None:
        """Release sectors back to the free space map.

        Merges with adjacent free entries where possible.

        Args:
            start_sector: First sector to free.
            num_sectors: Number of sectors to free.

        Raises:
            ValueError: If num_sectors is not positive.
        """
        if num_sectors <= 0:
            raise ValueError(f"num_sectors must be positive, got {num_sectors}")

        end_sector = start_sector + num_sectors
        n = self.num_entries

        # Find entries that are adjacent to the freed region
        merge_before = None  # Index of entry ending at start_sector
        merge_after = None   # Index of entry starting at end_sector

        for i in range(n):
            offset = i * _BYTES_PER_ENTRY
            entry_start = _read_24bit_le(self._data, _FREE_START_OFFSET + offset)
            entry_length = _read_24bit_le(self._data, _FREE_LEN_OFFSET + offset)
            entry_end = entry_start + entry_length

            if entry_end == start_sector:
                merge_before = i
            if entry_start == end_sector:
                merge_after = i

        if merge_before is not None and merge_after is not None:
            # Merge all three: extend the before-entry to cover the after-entry too
            before_offset = merge_before * _BYTES_PER_ENTRY
            after_offset = merge_after * _BYTES_PER_ENTRY
            before_start = _read_24bit_le(self._data, _FREE_START_OFFSET + before_offset)
            before_length = _read_24bit_le(self._data, _FREE_LEN_OFFSET + before_offset)
            after_length = _read_24bit_le(self._data, _FREE_LEN_OFFSET + after_offset)
            new_length = before_length + num_sectors + after_length
            _write_24bit_le(self._data, _FREE_LEN_OFFSET + before_offset, new_length)
            # Remove the after-entry
            self._remove_entry(merge_after, n)
        elif merge_before is not None:
            # Extend the before-entry
            before_offset = merge_before * _BYTES_PER_ENTRY
            before_length = _read_24bit_le(self._data, _FREE_LEN_OFFSET + before_offset)
            _write_24bit_le(self._data, _FREE_LEN_OFFSET + before_offset, before_length + num_sectors)
        elif merge_after is not None:
            # Extend the after-entry backward
            after_offset = merge_after * _BYTES_PER_ENTRY
            after_length = _read_24bit_le(self._data, _FREE_LEN_OFFSET + after_offset)
            _write_24bit_le(self._data, _FREE_START_OFFSET + after_offset, start_sector)
            _write_24bit_le(self._data, _FREE_LEN_OFFSET + after_offset, after_length + num_sectors)
        else:
            # Insert a new entry in sorted order
            insert_at = 0
            for i in range(n):
                offset = i * _BYTES_PER_ENTRY
                entry_start = _read_24bit_le(self._data, _FREE_START_OFFSET + offset)
                if entry_start > start_sector:
                    break
                insert_at = i + 1
            self._insert_entry(insert_at, n, start_sector, num_sectors)

        self._recalculate_checksums()

    def _remove_entry(self, index: int, num_entries: int) -> None:
        """Remove free space entry at index, shifting subsequent entries down."""
        for i in range(index, num_entries - 1):
            src = (i + 1) * _BYTES_PER_ENTRY
            dst = i * _BYTES_PER_ENTRY
            for b in range(_BYTES_PER_ENTRY):
                self._data[_FREE_START_OFFSET + dst + b] = self._data[_FREE_START_OFFSET + src + b]
                self._data[_FREE_LEN_OFFSET + dst + b] = self._data[_FREE_LEN_OFFSET + src + b]
        # Clear the last slot
        last = (num_entries - 1) * _BYTES_PER_ENTRY
        for b in range(_BYTES_PER_ENTRY):
            self._data[_FREE_START_OFFSET + last + b] = 0
            self._data[_FREE_LEN_OFFSET + last + b] = 0
        # Decrement FreeEnd
        self._data[_FREE_END_OFFSET] = (num_entries - 1) * _BYTES_PER_ENTRY

    def _insert_entry(self, index: int, num_entries: int, start: int, length: int) -> None:
        """Insert a new free space entry at index, shifting subsequent entries up."""
        # Shift entries up
        for i in range(num_entries - 1, index - 1, -1):
            src = i * _BYTES_PER_ENTRY
            dst = (i + 1) * _BYTES_PER_ENTRY
            for b in range(_BYTES_PER_ENTRY):
                self._data[_FREE_START_OFFSET + dst + b] = self._data[_FREE_START_OFFSET + src + b]
                self._data[_FREE_LEN_OFFSET + dst + b] = self._data[_FREE_LEN_OFFSET + src + b]
        # Write new entry
        offset = index * _BYTES_PER_ENTRY
        _write_24bit_le(self._data, _FREE_START_OFFSET + offset, start)
        _write_24bit_le(self._data, _FREE_LEN_OFFSET + offset, length)
        # Increment FreeEnd
        self._data[_FREE_END_OFFSET] = (num_entries + 1) * _BYTES_PER_ENTRY

    def _recalculate_checksums(self) -> None:
        """Recalculate and write both sector checksums."""
        self._data[_CHECK_0_OFFSET] = 0
        self._data[_CHECK_1_OFFSET] = 0
        self._data[_CHECK_0_OFFSET] = _calculate_old_map_checksum(self._data, 0x000)
        self._data[_CHECK_1_OFFSET] = _calculate_old_map_checksum(self._data, 0x100)

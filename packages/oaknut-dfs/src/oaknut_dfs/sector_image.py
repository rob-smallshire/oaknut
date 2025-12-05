"""Layer 2: Sector-level access abstraction for disk images.

This layer converts logical sector numbers to physical byte offsets and handles
disk geometry. It works with any buffer-protocol object (mmap, bytearray, memoryview).
"""

from abc import ABC, abstractmethod
from typing import Union
from oaknut_dfs.sectors_view import SectorsView


class SectorImage(ABC):
    """Abstract base class for sector-level disk access.

    Takes any buffer-protocol object and provides logical sector addressing
    with support for different physical layouts (sequential, interleaved, etc.).
    """

    SECTOR_SIZE = 256
    ACORN_DFS_SECTORS_PER_TRACK = 10

    def __init__(self, buffer, sectors_per_track: int = ACORN_DFS_SECTORS_PER_TRACK):
        """
        Initialize sector access layer.

        Args:
            buffer: Any buffer-protocol object (bytes, bytearray, memoryview, mmap)
            sectors_per_track: Number of sectors per track (default: 10 for Acorn DFS)
        """
        self._buffer = memoryview(buffer)
        self._sectors_per_track = sectors_per_track

    @property
    def sectors_per_track(self) -> int:
        """Get number of sectors per track for this disk format."""
        return self._sectors_per_track

    @property
    def track_size(self) -> int:
        """Get track size in bytes (sectors_per_track * SECTOR_SIZE)."""
        return self._sectors_per_track * self.SECTOR_SIZE

    @property
    def num_sides(self) -> int:
        """
        Get number of sides for this disk format.

        Returns:
            1 for single-sided, 2 for double-sided
        """
        return 1  # Default to single-sided; subclasses override if needed

    def format_description(self) -> str:
        """
        Get a human-readable description of this disk format.

        Returns:
            Format description string (e.g., "SSD 40T", "DSD 80T")
        """
        total_sectors = self.num_sectors()
        tracks = total_sectors // self._sectors_per_track

        if self.num_sides == 1:
            return f"SSD {tracks}T"
        else:
            tracks_per_side = tracks // self.num_sides
            return f"DSD {tracks_per_side}T"

    @abstractmethod
    def physical_offset(self, logical_sector: int) -> int:
        """
        Convert logical sector number to physical byte offset.

        Args:
            logical_sector: Logical sector number (0-based)

        Returns:
            Physical byte offset in the disk image

        Raises:
            ValueError: If logical_sector is negative or exceeds disk size
        """
        pass

    def num_sectors(self) -> int:
        """
        Get total number of logical sectors.

        Returns:
            Total number of sectors
        """
        return len(self._buffer) // self.SECTOR_SIZE

    def get_sector(self, sector: int) -> memoryview:
        """
        Get view of a single 256-byte sector.

        Args:
            sector: Logical sector number (0-based)

        Returns:
            memoryview of 256 bytes

        Raises:
            ValueError: If sector number is invalid
        """
        if sector < 0:
            raise ValueError(f"Sector number cannot be negative: {sector}")
        if sector >= self.num_sectors():
            raise ValueError(
                f"Sector {sector} exceeds disk size "
                f"(max sector: {self.num_sectors() - 1})"
            )

        offset = self.physical_offset(sector)
        return self._buffer[offset:offset + self.SECTOR_SIZE]

    def read_sector(self, sector: int) -> bytes:
        """
        Read a complete 256-byte sector (compatibility method).

        This method exists for backward compatibility with code expecting bytes.
        For zero-copy access, use get_sector() which returns a memoryview.

        Args:
            sector: Logical sector number (0-based)

        Returns:
            256 bytes of sector data

        Raises:
            ValueError: If sector number is invalid
        """
        return bytes(self.get_sector(sector))

    def get_sectors(self, start: int, count: int) -> SectorsView:
        """
        Get view of multiple consecutive logical sectors.

        Returns SectorsView wrapping the requested sectors.

        Args:
            start: First sector to read
            count: Number of sectors to read

        Returns:
            SectorsView wrapping the sectors

        Raises:
            ValueError: If sector range is invalid
        """
        if count < 0:
            raise ValueError(f"Count cannot be negative: {count}")
        if count == 0:
            return SectorsView([])
        if start < 0:
            raise ValueError(f"Start sector cannot be negative: {start}")
        if start + count > self.num_sectors():
            raise ValueError(
                f"Sector range {start}-{start + count - 1} exceeds disk size "
                f"(max sector: {self.num_sectors() - 1})"
            )

        # Always create a list of views, one per sector
        # SectorsView handles everything uniformly
        views = [self.get_sector(start + i) for i in range(count)]
        return SectorsView(views)

    def write_sector(self, sector: int, data: bytes) -> None:
        """
        Write a complete 256-byte sector.

        Args:
            sector: Logical sector number (0-based)
            data: Sector data (must be exactly 256 bytes)

        Raises:
            ValueError: If sector number is invalid or data size is wrong
        """
        if sector < 0:
            raise ValueError(f"Sector number cannot be negative: {sector}")
        if sector >= self.num_sectors():
            raise ValueError(
                f"Sector {sector} exceeds disk size "
                f"(max sector: {self.num_sectors() - 1})"
            )
        if len(data) != self.SECTOR_SIZE:
            raise ValueError(
                f"Sector data must be exactly {self.SECTOR_SIZE} bytes, "
                f"got {len(data)}"
            )

        offset = self.physical_offset(sector)
        self._buffer[offset:offset + self.SECTOR_SIZE] = data

    def write_sectors(self, start: int, data: bytes) -> None:
        """
        Write multiple consecutive logical sectors.

        Args:
            start: First sector to write
            data: Data to write (must be multiple of 256 bytes)

        Raises:
            ValueError: If data size is not a multiple of sector size
        """
        if len(data) % self.SECTOR_SIZE != 0:
            raise ValueError(
                f"Data size must be multiple of {self.SECTOR_SIZE}, "
                f"got {len(data)}"
            )

        num_sectors = len(data) // self.SECTOR_SIZE
        for i in range(num_sectors):
            sector_data = data[i * self.SECTOR_SIZE : (i + 1) * self.SECTOR_SIZE]
            self.write_sector(start + i, sector_data)


class SSDSectorImage(SectorImage):
    """Sequential single-sided disk sector access.

    SSD format uses simple sequential layout where logical sector N
    is at physical offset N * 256.
    """

    def physical_offset(self, logical_sector: int) -> int:
        """
        Calculate physical offset for SSD format.

        SSD uses simple sequential layout:
        - Sector 0 → Offset 0
        - Sector 1 → Offset 256
        - Sector N → Offset N * 256
        """
        return logical_sector * self.SECTOR_SIZE


class SequentialDSDSectorImage(SectorImage):
    """Sequential double-sided disk sector access.

    Sequential DSD layout stores all tracks from side 0, then all tracks
    from side 1. Addressing is simple and sequential like SSD.
    """

    @property
    def num_sides(self) -> int:
        """Get number of sides (always 2 for DSD)."""
        return 2

    def physical_offset(self, logical_sector: int) -> int:
        """
        Calculate physical offset for sequential DSD format.

        Sequential DSD layout:
        - All tracks from side 0 first
        - Then all tracks from side 1
        - Simple sequential addressing like SSD
        """
        return logical_sector * self.SECTOR_SIZE


class InterleavedDSDSectorImage(SectorImage):
    """Interleaved double-sided disk sector access.

    Interleaved DSD alternates tracks between sides:
    - Side 0 Track 0 (sectors 0-9)
    - Side 1 Track 0 (sectors 10-19)
    - Side 0 Track 1 (sectors 20-29)
    - Side 1 Track 1 (sectors 30-39)
    - etc.

    This is the most common DSD format.
    """

    def __init__(self, buffer, tracks_per_side: int = 40, sectors_per_track: int = SectorImage.ACORN_DFS_SECTORS_PER_TRACK):
        """
        Initialize interleaved DSD sector access.

        Args:
            buffer: Underlying buffer
            tracks_per_side: Number of tracks per side (40 or 80, default: 40)
            sectors_per_track: Number of sectors per track (default: 10 for Acorn DFS)
        """
        super().__init__(buffer, sectors_per_track)
        self._tracks_per_side = tracks_per_side

    @property
    def num_sides(self) -> int:
        """Get number of sides (always 2 for DSD)."""
        return 2

    def physical_offset(self, logical_sector: int) -> int:
        """
        Calculate physical offset for interleaved DSD format.

        Interleaved DSD layout:
        - Tracks alternate between sides
        - Logical sectors increment sequentially: 0, 1, 2, ...
        - Physical layout has side 0 track 0, then side 1 track 0, etc.

        Physical layout:
        - Side 0 Track 0 (bytes 0-2559)
        - Side 1 Track 0 (bytes 2560-5119)
        - Side 0 Track 1 (bytes 5120-7679)
        - Side 1 Track 1 (bytes 7680-10239)
        - etc.
        """
        track = logical_sector // self._sectors_per_track
        sector_in_track = logical_sector % self._sectors_per_track
        side = track % 2
        physical_track = track // 2

        offset = (
            physical_track * self.track_size * 2  # Skip complete track pairs
            + side * self.track_size  # Offset to correct side
            + sector_in_track * self.SECTOR_SIZE  # Offset within track
        )

        return offset


class SSDSideSectorImage(SectorImage):
    """Access a single-sided disk as "side 0" (for API consistency with DSD).

    This is a simple wrapper that provides the same interface as DSDSideSectorImage
    for single-sided disks, allowing uniform handling of both SSD and DSD formats.

    Args:
        underlying: The single-sided SectorImage to wrap
        side: Side number (must be 0 for SSD, but accepted for API consistency)
        tracks_per_side: Number of tracks (40 or 80)
    """

    def __init__(self, underlying: SectorImage, side: int, tracks_per_side: int):
        """Initialize SSD side wrapper.

        Args:
            underlying: The underlying single-sided sector image
            side: Side number (must be 0 for single-sided disk)
            tracks_per_side: Number of tracks (40 or 80)

        Raises:
            ValueError: If side is not 0
        """
        if side != 0:
            raise ValueError(f"SSD only supports side 0, got side {side}")

        super().__init__(underlying._buffer, underlying._sectors_per_track)
        self._underlying = underlying
        self._tracks_per_side = tracks_per_side

    def physical_offset(self, logical_sector: int) -> int:
        """Pass through to underlying sector image."""
        return self._underlying.physical_offset(logical_sector)

    def num_sectors(self) -> int:
        """Return number of sectors (tracks * sectors_per_track)."""
        return self._tracks_per_side * self._sectors_per_track


class DSDSideSectorImage(SectorImage):
    """Access one side of an interleaved DSD disk.

    This class wraps an InterleavedDSDSectorImage and provides logical
    sector addressing (0-399 for 40-track) for a single side, with independent
    catalog management per side as required by DFS.

    Each side of a DSD disk:
    - Has its own sector numbering (0-399 for 40T, 0-799 for 80T)
    - Has its own catalog in sectors 0-1
    - Is completely independent from the other side

    Args:
        underlying: The InterleavedDSDSectorImage to wrap
        side: Which side to access (0 or 1)
        tracks_per_side: Number of tracks per side (40 or 80)
    """

    def __init__(
        self,
        underlying: Union[InterleavedDSDSectorImage, SequentialDSDSectorImage],
        side: int,
        tracks_per_side: int,
    ):
        """Initialize DSD side sector access.

        Args:
            underlying: The DSD sector image (interleaved or sequential)
            side: Side number (0 or 1)
            tracks_per_side: Number of tracks per side (40 or 80)

        Raises:
            ValueError: If side is not 0 or 1
        """
        if side not in (0, 1):
            raise ValueError(f"Invalid side: {side} (must be 0 or 1)")

        super().__init__(underlying._buffer, underlying._sectors_per_track)
        self._underlying = underlying
        self._side = side
        self._tracks_per_side = tracks_per_side

    def physical_offset(self, logical_sector: int) -> int:
        """
        Calculate physical offset for a logical sector on this side.

        Maps logical sectors (0-399 for 40T) on the selected side to physical
        sectors in the interleaved or sequential layout.

        Args:
            logical_sector: Logical sector number on this side

        Returns:
            Physical byte offset in disk image

        Raises:
            ValueError: If logical_sector is out of range
        """
        max_sector = self._tracks_per_side * self._sectors_per_track
        if not 0 <= logical_sector < max_sector:
            raise ValueError(
                f"Invalid sector: {logical_sector} "
                f"(must be 0-{max_sector-1} for {self._tracks_per_side} tracks)"
            )

        # Map logical sector on this side to physical interleaved/sequential sector
        track_on_side = logical_sector // self._sectors_per_track
        sector_in_track = logical_sector % self._sectors_per_track

        # Calculate physical sector number based on format
        if isinstance(self._underlying, InterleavedDSDSectorImage):
            # Interleaved: each track pair occupies sectors_per_track * 2 sectors
            physical_sector = (
                track_on_side * 2 * self._sectors_per_track  # Skip to correct track pair
                + self._side * self._sectors_per_track  # Offset for side
                + sector_in_track  # Sector within track
            )
        else:
            # Sequential: side 0 first, then side 1
            physical_sector = (
                self._side * self._tracks_per_side * self._sectors_per_track
                + track_on_side * self._sectors_per_track
                + sector_in_track
            )

        return self._underlying.physical_offset(physical_sector)

    def num_sectors(self) -> int:
        """Return number of sectors on this side."""
        return self._tracks_per_side * self._sectors_per_track

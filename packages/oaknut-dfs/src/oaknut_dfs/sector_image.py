"""Layer 2: Sector-level access abstraction for disk images."""

from abc import ABC, abstractmethod
from oaknut_dfs.disk_image import DiskImage


class SectorImage(ABC):
    """Abstract base class for sector-level disk access."""

    SECTOR_SIZE = 256
    SECTORS_PER_TRACK = 10
    TRACK_SIZE = SECTOR_SIZE * SECTORS_PER_TRACK  # 2560 bytes

    def __init__(self, disk_image: DiskImage):
        """
        Initialize sector access layer.

        Args:
            disk_image: Underlying disk image storage
        """
        self._disk_image = disk_image

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
        return self._disk_image.size() // self.SECTOR_SIZE

    def read_sector(self, sector: int) -> bytes:
        """
        Read a complete 256-byte sector.

        Args:
            sector: Logical sector number (0-based)

        Returns:
            256 bytes of sector data

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
        return self._disk_image.read_bytes(offset, self.SECTOR_SIZE)

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
        self._disk_image.write_bytes(offset, data)

    def read_sectors(self, start_sector: int, count: int) -> bytes:
        """
        Read multiple consecutive logical sectors.

        Args:
            start_sector: First sector to read
            count: Number of sectors to read

        Returns:
            Concatenated sector data

        Raises:
            ValueError: If sector range is invalid
        """
        if count < 0:
            raise ValueError(f"Count cannot be negative: {count}")
        if count == 0:
            return b""

        data = bytearray()
        for i in range(count):
            data.extend(self.read_sector(start_sector + i))
        return bytes(data)

    def write_sectors(self, start_sector: int, data: bytes) -> None:
        """
        Write multiple consecutive logical sectors.

        Args:
            start_sector: First sector to write
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
            self.write_sector(start_sector + i, sector_data)


class SSDSectorImage(SectorImage):
    """Sequential single-sided disk sector access."""

    def physical_offset(self, logical_sector: int) -> int:
        """
        Calculate physical offset for SSD format.

        SSD uses simple sequential layout:
        Sector 0 -> Offset 0
        Sector 1 -> Offset 256
        Sector N -> Offset N * 256
        """
        return logical_sector * self.SECTOR_SIZE


class SequentialDSDSectorImage(SectorImage):
    """Sequential double-sided disk sector access."""

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
    """Interleaved double-sided disk sector access."""

    def __init__(self, disk_image: DiskImage, tracks_per_side: int = 40):
        """
        Initialize interleaved DSD sector access.

        Args:
            disk_image: Underlying disk image storage
            tracks_per_side: Number of tracks per side (default: 40)
        """
        super().__init__(disk_image)
        self._tracks_per_side = tracks_per_side

    def physical_offset(self, logical_sector: int) -> int:
        """
        Calculate physical offset for interleaved DSD format.

        Interleaved DSD layout:
        - Tracks alternate between sides
        - Side 0 Track 0: Sectors 0-9
        - Side 1 Track 0: Sectors 10-19
        - Side 0 Track 1: Sectors 20-29
        - Side 1 Track 1: Sectors 30-39
        - etc.

        Physical layout:
        - Side 0 Track 0 (bytes 0-2559)
        - Side 1 Track 0 (bytes 2560-5119)
        - Side 0 Track 1 (bytes 5120-7679)
        - Side 1 Track 1 (bytes 7680-10239)
        - etc.
        """
        track = logical_sector // self.SECTORS_PER_TRACK
        sector_in_track = logical_sector % self.SECTORS_PER_TRACK
        side = track % 2
        physical_track = track // 2

        offset = (
            physical_track * self.TRACK_SIZE * 2  # Skip complete track pairs
            + side * self.TRACK_SIZE  # Offset to correct side
            + sector_in_track * self.SECTOR_SIZE  # Offset within track
        )

        return offset

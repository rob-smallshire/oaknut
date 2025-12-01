"""Layer 3: Catalog management for DFS disk images."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from oaknut_dfs.sector_image import SectorImage
import oaknut_dfs.acorn_encoding  # Register Acorn codec


@dataclass
class FileEntry:
    """Represents a file entry in the DFS catalog."""

    filename: str  # 7 characters max, without directory prefix
    directory: str  # Single character directory prefix
    locked: bool
    load_address: int  # 18-bit (or 32-bit with sign extension)
    exec_address: int  # 18-bit (or 32-bit with sign extension)
    length: int  # 18-bit
    start_sector: int  # 10-bit sector number

    @property
    def full_name(self) -> str:
        """Return the full filename with directory prefix."""
        return f"{self.directory}.{self.filename.rstrip()}"

    @property
    def sectors_required(self) -> int:
        """Calculate number of sectors needed for this file."""
        return (self.length + 255) // 256


@dataclass
class DiskInfo:
    """Disk catalog metadata."""

    title: str  # 12 characters max
    cycle_number: int  # Sequence number
    num_files: int
    total_sectors: int  # 10-bit value
    boot_option: int  # 0-3


class Catalog(ABC):
    """Abstract base class for DFS catalog management."""

    def __init__(self, sector_image: SectorImage):
        """
        Initialize catalog with sector access layer.

        Args:
            sector_image: Sector-level disk access
        """
        self._sector_image = sector_image

    @abstractmethod
    def read_disk_info(self) -> DiskInfo:
        """
        Read catalog metadata.

        Returns:
            DiskInfo with catalog metadata
        """
        pass

    @abstractmethod
    def write_disk_info(self, info: DiskInfo) -> None:
        """
        Write catalog metadata.

        Args:
            info: Disk information to write
        """
        pass

    @abstractmethod
    def list_files(self) -> list[FileEntry]:
        """
        List all file entries.

        Returns:
            List of FileEntry objects
        """
        pass

    @abstractmethod
    def find_file(self, filename: str) -> Optional[FileEntry]:
        """
        Find a file by full name.

        Args:
            filename: Full filename (e.g., '$.HELLO')

        Returns:
            FileEntry if found, None otherwise
        """
        pass

    @abstractmethod
    def add_file_entry(self, entry: FileEntry) -> None:
        """
        Add a new file entry to catalog.

        Args:
            entry: File entry to add

        Raises:
            ValueError: If catalog is full or entry is invalid
        """
        pass

    @abstractmethod
    def remove_file_entry(self, filename: str) -> None:
        """
        Remove a file entry from catalog.

        Args:
            filename: Full filename (e.g., '$.HELLO')

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is locked
        """
        pass

    @abstractmethod
    def validate(self) -> list[str]:
        """
        Validate catalog integrity.

        Returns:
            List of error messages (empty if valid)
        """
        pass


class AcornDFSCatalog(Catalog):
    """Standard Acorn DFS catalog implementation."""

    MAX_FILES = 31
    CATALOG_SECTOR_0 = 0
    CATALOG_SECTOR_1 = 1

    def read_disk_info(self) -> DiskInfo:
        """Read catalog metadata from sectors 0 and 1."""
        sector0 = self._sector_image.read_sector(self.CATALOG_SECTOR_0)
        sector1 = self._sector_image.read_sector(self.CATALOG_SECTOR_1)

        # Parse title (8 bytes from sector0, 4 from sector1) using Acorn encoding
        title_part1 = sector0[0:8].decode("acorn")
        title_part2 = sector1[0:4].decode("acorn")
        title = (title_part1 + title_part2).rstrip()

        # Parse metadata from sector1
        cycle = sector1[0x04]
        last_entry = sector1[0x05]
        extra = sector1[0x06]
        sectors_low = sector1[0x07]

        num_files = last_entry // 8
        total_sectors = sectors_low | ((extra & 0x03) << 8)
        boot_option = (extra >> 4) & 0x03

        return DiskInfo(
            title=title,
            cycle_number=cycle,
            num_files=num_files,
            total_sectors=total_sectors,
            boot_option=boot_option,
        )

    def write_disk_info(self, info: DiskInfo) -> None:
        """Write catalog metadata to sectors 0 and 1."""
        sector0 = bytearray(self._sector_image.read_sector(self.CATALOG_SECTOR_0))
        sector1 = bytearray(self._sector_image.read_sector(self.CATALOG_SECTOR_1))

        # Write title (pad to 12 characters) using Acorn encoding
        title = info.title[:12].ljust(12)
        sector0[0:8] = title[0:8].encode("acorn")
        sector1[0:4] = title[8:12].encode("acorn")

        # Write metadata to sector1
        sector1[0x04] = info.cycle_number & 0xFF
        sector1[0x05] = (info.num_files * 8) & 0xFF

        # Encode extra byte: bits 0-1 = high bits of total_sectors, bits 4-5 = boot_option
        sectors_high = (info.total_sectors >> 8) & 0x03
        extra = sectors_high | ((info.boot_option & 0x03) << 4)
        sector1[0x06] = extra

        sector1[0x07] = info.total_sectors & 0xFF

        # Write back
        self._sector_image.write_sector(self.CATALOG_SECTOR_0, bytes(sector0))
        self._sector_image.write_sector(self.CATALOG_SECTOR_1, bytes(sector1))

    def list_files(self) -> list[FileEntry]:
        """Read all file entries from the catalog."""
        disk_info = self.read_disk_info()
        files = []

        sector0 = self._sector_image.read_sector(self.CATALOG_SECTOR_0)
        sector1 = self._sector_image.read_sector(self.CATALOG_SECTOR_1)

        for i in range(disk_info.num_files):
            entry_offset = 8 + (i * 8)  # Start after disk title

            # Read from sector 0 (filename and directory) using Acorn encoding
            filename_bytes = sector0[entry_offset : entry_offset + 7]
            filename = filename_bytes.decode("acorn")
            dir_byte = sector0[entry_offset + 7]

            directory = chr(dir_byte & 0x7F)
            locked = (dir_byte & 0x80) != 0

            # Read from sector 1 (addresses and metadata)
            sector1_offset = entry_offset
            load_low = sector1[sector1_offset] | (sector1[sector1_offset + 1] << 8)
            exec_low = sector1[sector1_offset + 2] | (sector1[sector1_offset + 3] << 8)
            length_low = sector1[sector1_offset + 4] | (sector1[sector1_offset + 5] << 8)
            extra_byte = sector1[sector1_offset + 6]
            sector_low = sector1[sector1_offset + 7]

            # Reconstruct 18-bit values
            load_addr = load_low | ((extra_byte & 0x0C) << 14)
            exec_addr = exec_low | ((extra_byte & 0xC0) << 10)
            length = length_low | ((extra_byte & 0x30) << 12)
            start_sector = sector_low | ((extra_byte & 0x03) << 8)

            # Handle sign extension for I/O processor addresses (0xFFFFxxxx range)
            if load_addr & 0x30000 == 0x30000:
                load_addr |= 0xFFFC0000
            if exec_addr & 0x30000 == 0x30000:
                exec_addr |= 0xFFFC0000

            files.append(
                FileEntry(
                    filename=filename,
                    directory=directory,
                    locked=locked,
                    load_address=load_addr,
                    exec_address=exec_addr,
                    length=length,
                    start_sector=start_sector,
                )
            )

        return files

    def find_file(self, filename: str) -> Optional[FileEntry]:
        """Find a file by full name."""
        files = self.list_files()
        for entry in files:
            if entry.full_name.upper() == filename.upper():
                return entry
        return None

    def add_file_entry(self, entry: FileEntry) -> None:
        """Add a new file entry to catalog."""
        disk_info = self.read_disk_info()

        if disk_info.num_files >= self.MAX_FILES:
            raise ValueError(f"Catalog is full (max {self.MAX_FILES} files)")

        # Validate filename
        if len(entry.filename) > 7:
            raise ValueError(f"Filename too long: {entry.filename} (max 7 characters)")
        if len(entry.directory) != 1:
            raise ValueError(f"Directory must be single character: {entry.directory}")

        # Check if file already exists
        if self.find_file(entry.full_name) is not None:
            raise ValueError(f"File already exists: {entry.full_name}")

        # Read current sectors
        sector0 = bytearray(self._sector_image.read_sector(self.CATALOG_SECTOR_0))
        sector1 = bytearray(self._sector_image.read_sector(self.CATALOG_SECTOR_1))

        # Calculate entry offset
        entry_offset = 8 + (disk_info.num_files * 8)

        # Write to sector 0 (filename and directory) using Acorn encoding
        filename_padded = entry.filename.ljust(7)
        sector0[entry_offset : entry_offset + 7] = filename_padded.encode("acorn")
        dir_byte = ord(entry.directory) & 0x7F
        if entry.locked:
            dir_byte |= 0x80
        sector0[entry_offset + 7] = dir_byte

        # Write to sector 1 (addresses and metadata)
        sector1_offset = entry_offset

        # Encode load address (low 16 bits)
        load_low = entry.load_address & 0xFFFF
        sector1[sector1_offset] = load_low & 0xFF
        sector1[sector1_offset + 1] = (load_low >> 8) & 0xFF

        # Encode exec address (low 16 bits)
        exec_low = entry.exec_address & 0xFFFF
        sector1[sector1_offset + 2] = exec_low & 0xFF
        sector1[sector1_offset + 3] = (exec_low >> 8) & 0xFF

        # Encode length (low 16 bits)
        length_low = entry.length & 0xFFFF
        sector1[sector1_offset + 4] = length_low & 0xFF
        sector1[sector1_offset + 5] = (length_low >> 8) & 0xFF

        # Encode extra byte with high bits
        extra_byte = (
            ((entry.start_sector >> 8) & 0x03)  # Bits 0-1: start sector high
            | (((entry.load_address >> 14) & 0x0C))  # Bits 2-3: load address high
            | (((entry.length >> 12) & 0x30))  # Bits 4-5: length high
            | (((entry.exec_address >> 10) & 0xC0))  # Bits 6-7: exec address high
        )
        sector1[sector1_offset + 6] = extra_byte

        # Encode start sector (low 8 bits)
        sector1[sector1_offset + 7] = entry.start_sector & 0xFF

        # Write back sectors
        self._sector_image.write_sector(self.CATALOG_SECTOR_0, bytes(sector0))
        self._sector_image.write_sector(self.CATALOG_SECTOR_1, bytes(sector1))

        # Update disk info
        disk_info.num_files += 1
        disk_info.cycle_number = (disk_info.cycle_number + 1) & 0xFF
        self.write_disk_info(disk_info)

    def remove_file_entry(self, filename: str) -> None:
        """Remove a file entry from catalog."""
        entry = self.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")
        if entry.locked:
            raise PermissionError(f"File is locked: {filename}")

        files = self.list_files()
        disk_info = self.read_disk_info()

        # Find index of file to remove
        file_index = None
        for i, f in enumerate(files):
            if f.full_name.upper() == filename.upper():
                file_index = i
                break

        if file_index is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Remove from list
        files.pop(file_index)

        # Rebuild catalog
        sector0 = bytearray(256)
        sector1 = bytearray(256)

        # Preserve title and metadata structure
        old_sector0 = self._sector_image.read_sector(self.CATALOG_SECTOR_0)
        old_sector1 = self._sector_image.read_sector(self.CATALOG_SECTOR_1)

        sector0[0:8] = old_sector0[0:8]  # Title part 1
        sector1[0:8] = old_sector1[0:8]  # Title part 2 + metadata

        # Write remaining files
        for i, f in enumerate(files):
            entry_offset = 8 + (i * 8)

            # Write to sector 0 using Acorn encoding
            filename_padded = f.filename.ljust(7)
            sector0[entry_offset : entry_offset + 7] = filename_padded.encode("acorn")
            dir_byte = ord(f.directory) & 0x7F
            if f.locked:
                dir_byte |= 0x80
            sector0[entry_offset + 7] = dir_byte

            # Write to sector 1
            sector1_offset = entry_offset

            load_low = f.load_address & 0xFFFF
            sector1[sector1_offset] = load_low & 0xFF
            sector1[sector1_offset + 1] = (load_low >> 8) & 0xFF

            exec_low = f.exec_address & 0xFFFF
            sector1[sector1_offset + 2] = exec_low & 0xFF
            sector1[sector1_offset + 3] = (exec_low >> 8) & 0xFF

            length_low = f.length & 0xFFFF
            sector1[sector1_offset + 4] = length_low & 0xFF
            sector1[sector1_offset + 5] = (length_low >> 8) & 0xFF

            extra_byte = (
                ((f.start_sector >> 8) & 0x03)
                | (((f.load_address >> 14) & 0x0C))
                | (((f.length >> 12) & 0x30))
                | (((f.exec_address >> 10) & 0xC0))
            )
            sector1[sector1_offset + 6] = extra_byte
            sector1[sector1_offset + 7] = f.start_sector & 0xFF

        # Write back sectors
        self._sector_image.write_sector(self.CATALOG_SECTOR_0, bytes(sector0))
        self._sector_image.write_sector(self.CATALOG_SECTOR_1, bytes(sector1))

        # Update disk info
        disk_info.num_files = len(files)
        disk_info.cycle_number = (disk_info.cycle_number + 1) & 0xFF
        self.write_disk_info(disk_info)

    def validate(self) -> list[str]:
        """Validate catalog integrity."""
        errors = []

        try:
            disk_info = self.read_disk_info()
        except Exception as e:
            errors.append(f"Failed to read disk info: {e}")
            return errors

        # Check number of files
        if disk_info.num_files < 0:
            errors.append(f"Invalid number of files: {disk_info.num_files}")
        if disk_info.num_files > self.MAX_FILES:
            errors.append(
                f"Too many files: {disk_info.num_files} (max {self.MAX_FILES})"
            )

        # Check boot option
        if disk_info.boot_option not in [0, 1, 2, 3]:
            errors.append(f"Invalid boot option: {disk_info.boot_option}")

        # Try to read files
        try:
            files = self.list_files()

            # Check for duplicate filenames
            names = [f.full_name.upper() for f in files]
            duplicates = set([n for n in names if names.count(n) > 1])
            if duplicates:
                errors.append(f"Duplicate filenames: {', '.join(duplicates)}")

            # Check file entry validity
            for f in files:
                if len(f.filename) > 7:
                    errors.append(f"Filename too long: {f.full_name}")
                if f.start_sector < 2:
                    errors.append(
                        f"File {f.full_name} start sector {f.start_sector} "
                        f"overlaps catalog"
                    )
                if f.start_sector >= disk_info.total_sectors:
                    errors.append(
                        f"File {f.full_name} start sector {f.start_sector} "
                        f"exceeds disk size"
                    )

        except Exception as e:
            errors.append(f"Failed to read files: {e}")

        return errors

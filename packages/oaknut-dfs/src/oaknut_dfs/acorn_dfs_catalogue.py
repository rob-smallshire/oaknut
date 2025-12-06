"""Acorn DFS catalog implementation."""

from oaknut_dfs.catalogue import Catalogue, DiskInfo, FileEntry, ParsedFilename
from oaknut_dfs.surface import Surface


class AcornDFSCatalogue(Catalogue):
    """Acorn DFS catalog implementation (sectors 0-1, max 31 files)."""

    # Constants
    MAX_FILES = 31
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 2
    MAX_FILENAME_LENGTH = 7
    MAX_TITLE_LENGTH = 12
    VALID_DIRECTORY_CHARS = "$ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(self, surface: Surface):
        super().__init__(surface)

    @property
    def max_files(self) -> int:
        return self.MAX_FILES

    def get_disk_info(self) -> DiskInfo:
        """Read disk info from sectors 0-1."""
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Parse title (8 bytes from sector 0 + 4 bytes from sector 1)
        title_part1 = bytes(sector0[0:8]).decode("acorn")
        title_part2 = bytes(sector1[0:4]).decode("acorn")
        title = (title_part1 + title_part2).rstrip()

        # Parse metadata from sector 1
        cycle_number = sector1[4]
        num_files = sector1[5] // 8  # Last entry byte / 8
        extra_byte = sector1[6]
        sector_count_low = sector1[7]

        total_sectors = sector_count_low | ((extra_byte & 0x03) << 8)
        boot_option = (extra_byte >> 4) & 0x03

        return DiskInfo(
            title=title,
            cycle_number=cycle_number,
            num_files=num_files,
            total_sectors=total_sectors,
            boot_option=boot_option,
        )

    def list_files(self) -> list[FileEntry]:
        """List all files from catalog sectors 0-1."""
        disk_info = self.get_disk_info()
        if disk_info.num_files == 0:
            return []

        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        files = []
        for i in range(disk_info.num_files):
            # Each file entry spans both sectors
            entry_offset = 8 + (i * 8)

            # Parse from sector 0 (filename + directory)
            filename = bytes(sector0[entry_offset : entry_offset + 7]).decode("acorn").rstrip()
            dir_byte = sector0[entry_offset + 7]
            directory = chr(dir_byte & 0x7F)
            locked = bool(dir_byte & 0x80)

            # Parse from sector 1 (addresses, length, sector)
            sector1_offset = entry_offset
            load_low = sector1[sector1_offset] | (sector1[sector1_offset + 1] << 8)
            exec_low = sector1[sector1_offset + 2] | (sector1[sector1_offset + 3] << 8)
            length_low = sector1[sector1_offset + 4] | (sector1[sector1_offset + 5] << 8)
            extra_byte = sector1[sector1_offset + 6]
            sector_low = sector1[sector1_offset + 7]

            # Unpack high bits from extra byte
            load_address = load_low | ((extra_byte & 0x0C) << 14)
            exec_address = exec_low | ((extra_byte & 0xC0) << 10)
            length = length_low | ((extra_byte & 0x30) << 12)
            start_sector = sector_low | ((extra_byte & 0x03) << 8)

            files.append(
                FileEntry(
                    filename=filename,
                    directory=directory,
                    locked=locked,
                    load_address=load_address,
                    exec_address=exec_address,
                    length=length,
                    start_sector=start_sector,
                )
            )

        return files

    def parse_filename(self, path: str) -> ParsedFilename:
        """Parse and validate Acorn DFS filename."""
        # Parse using base class helper
        directory, filename = self._default_parse_filename(path, default_directory="$")

        # Normalize to uppercase
        directory = directory.upper()
        filename = filename.upper()

        # Validate components
        self.validate_directory(directory)
        self.validate_filename(filename)

        return ParsedFilename(directory=directory, filename=filename)

    def validate_filename(self, filename: str) -> None:
        """Validate Acorn DFS filename constraints."""
        if not filename:
            raise ValueError("Filename cannot be empty")

        if len(filename) > self.MAX_FILENAME_LENGTH:
            raise ValueError(
                f"Filename too long: '{filename}' "
                f"(max {self.MAX_FILENAME_LENGTH} chars)"
            )

        # Validate Acorn encoding compatibility
        try:
            filename.encode('acorn')
        except (UnicodeEncodeError, LookupError) as e:
            raise ValueError(f"Filename contains invalid characters: {e}")

    def validate_directory(self, directory: str) -> None:
        """Validate Acorn DFS directory character."""
        if len(directory) != 1:
            raise ValueError(f"Directory must be single character, got: '{directory}'")

        if directory.upper() not in self.VALID_DIRECTORY_CHARS:
            raise ValueError(f"Invalid directory '{directory}'. Must be $ or A-Z")

    def validate_title(self, title: str) -> None:
        """Validate Acorn DFS title constraints."""
        if len(title) > self.MAX_TITLE_LENGTH:
            raise ValueError(
                f"Title too long: '{title}' (max {self.MAX_TITLE_LENGTH} chars)"
            )

        # Validate Acorn encoding compatibility
        try:
            title.encode('acorn')
        except (UnicodeEncodeError, LookupError) as e:
            raise ValueError(f"Title contains invalid characters: {e}")

    def add_file_entry(
        self,
        filename: str,
        directory: str,
        load_address: int,
        exec_address: int,
        length: int,
        start_sector: int,
        locked: bool = False,
    ) -> None:
        """Add file entry to catalog, increment cycle number."""
        # Validate inputs
        self.validate_filename(filename)
        self.validate_directory(directory)

        # Normalize to uppercase
        filename = filename.upper()
        directory = directory.upper()

        # Read current state
        disk_info = self.get_disk_info()

        if disk_info.num_files >= self.MAX_FILES:
            raise ValueError(f"Catalog full (max {self.MAX_FILES} files)")

        # Get catalog sectors individually
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Write to next available entry slot
        entry_offset = 8 + (disk_info.num_files * 8)

        # Write filename and directory to sector 0
        filename_padded = filename.ljust(7)
        sector0[entry_offset : entry_offset + 7] = filename_padded.encode("acorn")
        dir_byte = ord(directory) & 0x7F
        if locked:
            dir_byte |= 0x80
        sector0[entry_offset + 7] = dir_byte

        # Write addresses/length/sector to sector 1
        sector1_offset = entry_offset
        sector1[sector1_offset] = load_address & 0xFF
        sector1[sector1_offset + 1] = (load_address >> 8) & 0xFF
        sector1[sector1_offset + 2] = exec_address & 0xFF
        sector1[sector1_offset + 3] = (exec_address >> 8) & 0xFF
        sector1[sector1_offset + 4] = length & 0xFF
        sector1[sector1_offset + 5] = (length >> 8) & 0xFF

        # Pack high bits into extra byte
        extra_byte = (
            ((start_sector >> 8) & 0x03)
            | (((load_address >> 14) & 0x03) << 2)
            | (((length >> 12) & 0x03) << 4)
            | (((exec_address >> 10) & 0x03) << 6)
        )
        sector1[sector1_offset + 6] = extra_byte
        sector1[sector1_offset + 7] = start_sector & 0xFF

        # Update metadata: increment file count and cycle number
        sector1[5] = (disk_info.num_files + 1) * 8
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF

        # Sectors are already writable memoryviews - changes are persisted

    def remove_file_entry(self, filename: str) -> None:
        """Remove file from catalog, rebuild catalog."""
        # Find file
        entry = self.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        if entry.locked:
            raise PermissionError(f"File is locked: {filename}")

        # Get all files except the one to remove
        files = [f for f in self.list_files() if f.path.upper() != filename.upper()]

        # Rebuild catalog from scratch
        self._rebuild_catalog(files)

    def _rebuild_catalog(self, files: list[FileEntry]) -> None:
        """Rebuild catalog sectors from file list."""
        # Clear catalog sectors
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Get current disk info to preserve title and sector count
        disk_info = self.get_disk_info()

        # Clear everything
        sector0[:] = b"\x00" * 256
        sector1[:] = b"\x00" * 256

        # Restore title
        title_part1 = disk_info.title[:8].ljust(8)
        title_part2 = disk_info.title[8:12].ljust(4)
        sector0[0:8] = title_part1.encode("acorn")
        sector1[0:4] = title_part2.encode("acorn")

        # Write each file entry
        for i, entry in enumerate(files):
            entry_offset = 8 + (i * 8)

            # Write filename and directory to sector 0
            filename_padded = entry.filename.ljust(7)
            sector0[entry_offset : entry_offset + 7] = filename_padded.encode("acorn")
            dir_byte = ord(entry.directory) & 0x7F
            if entry.locked:
                dir_byte |= 0x80
            sector0[entry_offset + 7] = dir_byte

            # Write addresses/length/sector to sector 1
            sector1_offset = entry_offset
            sector1[sector1_offset] = entry.load_address & 0xFF
            sector1[sector1_offset + 1] = (entry.load_address >> 8) & 0xFF
            sector1[sector1_offset + 2] = entry.exec_address & 0xFF
            sector1[sector1_offset + 3] = (entry.exec_address >> 8) & 0xFF
            sector1[sector1_offset + 4] = entry.length & 0xFF
            sector1[sector1_offset + 5] = (entry.length >> 8) & 0xFF

            # Pack high bits into extra byte
            extra_byte = (
                ((entry.start_sector >> 8) & 0x03)
                | (((entry.load_address >> 14) & 0x03) << 2)
                | (((entry.length >> 12) & 0x03) << 4)
                | (((entry.exec_address >> 10) & 0x03) << 6)
            )
            sector1[sector1_offset + 6] = extra_byte
            sector1[sector1_offset + 7] = entry.start_sector & 0xFF

        # Update metadata
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF  # Increment cycle number
        sector1[5] = len(files) * 8  # Number of files
        sector1[6] = ((disk_info.total_sectors >> 8) & 0x03) | (
            disk_info.boot_option << 4
        )  # Extra byte
        sector1[7] = disk_info.total_sectors & 0xFF  # Sector count low

    def set_title(self, title: str) -> None:
        """Set disk title (max 12 chars)."""
        # Validate title
        self.validate_title(title)

        # Pad to 12 characters
        title = title.ljust(12)

        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Write title: first 8 chars to sector 0, next 4 to sector 1
        sector0[0:8] = title[:8].encode("acorn")
        sector1[0:4] = title[8:12].encode("acorn")

        # Increment cycle number
        disk_info = self.get_disk_info()
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF

    def set_boot_option(self, option: int) -> None:
        """Set boot option (0-3)."""
        if not 0 <= option <= 3:
            raise ValueError(f"Boot option must be 0-3, got {option}")

        sector1 = self._surface.sector_range(1, 1)
        disk_info = self.get_disk_info()

        # Update boot option in extra byte (bits 4-5)
        extra_byte = sector1[6]
        extra_byte = (extra_byte & 0xCF) | (option << 4)
        sector1[6] = extra_byte

        # Increment cycle number
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF

    def lock_file(self, filename: str) -> None:
        """Lock file to prevent deletion."""
        self._set_file_locked(filename, True)

    def unlock_file(self, filename: str) -> None:
        """Unlock file."""
        self._set_file_locked(filename, False)

    def _set_file_locked(self, filename: str, locked: bool) -> None:
        """Set locked status for a file."""
        # Find the file
        entry = self.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Find file index in catalog
        files = self.list_files()
        file_index = None
        for i, f in enumerate(files):
            if f.path.upper() == filename.upper():
                file_index = i
                break

        if file_index is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Calculate entry offset
        entry_offset = 8 + (file_index * 8)

        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Modify locked bit (bit 7 of directory byte)
        dir_byte = sector0[entry_offset + 7]
        if locked:
            dir_byte |= 0x80
        else:
            dir_byte &= 0x7F
        sector0[entry_offset + 7] = dir_byte

        # Increment cycle number
        disk_info = self.get_disk_info()
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF

    def rename_file(self, old_name: str, new_name: str) -> None:
        """Rename file preserving all metadata and location."""
        # Find the file
        entry = self.find_file(old_name)
        if entry is None:
            raise FileNotFoundError(f"File not found: {old_name}")

        # Parse and validate new name using new method
        parsed = self.parse_filename(new_name)
        new_filename = parsed.filename
        new_directory = parsed.directory

        # Find file index in catalog
        files = self.list_files()
        file_index = None
        for i, f in enumerate(files):
            if f.path.upper() == old_name.upper():
                file_index = i
                break

        if file_index is None:
            raise FileNotFoundError(f"File not found: {old_name}")

        # Calculate entry offset
        entry_offset = 8 + (file_index * 8)

        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Update filename and directory in sector 0
        new_filename_padded = new_filename.ljust(7)
        sector0[entry_offset:entry_offset + 7] = new_filename_padded.encode("acorn")

        # Preserve locked bit when setting directory
        dir_byte = ord(new_directory) & 0x7F
        if entry.locked:
            dir_byte |= 0x80
        sector0[entry_offset + 7] = dir_byte

        # Increment cycle number
        disk_info = self.get_disk_info()
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF

    def validate(self) -> list[str]:
        """
        Validate Acorn DFS catalogue integrity.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check catalog structure
        disk_info = self.get_disk_info()
        if disk_info.num_files > self.MAX_FILES:
            errors.append(
                f"Too many files: {disk_info.num_files} > {self.MAX_FILES}"
            )

        # Check for overlapping files
        files = self.list_files()
        sector_map = {}

        for entry in files:
            for sector in range(
                entry.start_sector, entry.start_sector + entry.sectors_required
            ):
                if sector in sector_map:
                    errors.append(
                        f"Sector {sector} used by both {sector_map[sector]} and {entry.path}"
                    )
                else:
                    sector_map[sector] = entry.path

        # Check files don't exceed disk bounds
        total_sectors = self._surface.num_sectors
        for entry in files:
            end_sector = entry.start_sector + entry.sectors_required
            if end_sector > total_sectors:
                errors.append(
                    f"File {entry.path} extends beyond disk: "
                    f"sector {end_sector} > {total_sectors}"
                )

        # Check for duplicate filenames
        names = [f.path.upper() for f in files]
        duplicates = [name for name in set(names) if names.count(name) > 1]
        if duplicates:
            errors.append(f"Duplicate filenames: {', '.join(duplicates)}")

        return errors

    def compact(self) -> int:
        """
        Compact Acorn DFS catalogue by removing fragmentation.

        Reads file data from sectors, then rewrites files sequentially
        starting from sector 2. This consolidates free space at the end.

        Returns:
            Number of files compacted

        Raises:
            PermissionError: If locked files present
        """
        files = self.list_files()

        # Check for locked files
        locked_files = [f for f in files if f.locked]
        if locked_files:
            names = ", ".join(f.path for f in locked_files)
            raise PermissionError(f"Cannot compact: locked files present: {names}")

        if not files:
            return 0

        # Read all file data from sectors (with metadata)
        file_data = []
        for entry in files:
            # Read the actual sectors containing file data
            sectors_view = self._surface.sector_range(entry.start_sector, entry.sectors_required)
            # Copy only the actual file data (trim padding)
            data = bytes(sectors_view[:entry.length])
            file_data.append(
                {
                    "filename": entry.filename,
                    "directory": entry.directory,
                    "data": data,
                    "load_address": entry.load_address,
                    "exec_address": entry.exec_address,
                    "locked": entry.locked,
                }
            )

        # Build new file entries with sequential sectors starting from sector 2
        new_entries = []
        next_sector = 2
        for file_info in file_data:
            sectors_needed = (len(file_info["data"]) + 255) // 256
            new_entries.append(
                FileEntry(
                    filename=file_info["filename"],
                    directory=file_info["directory"],
                    locked=file_info["locked"],
                    load_address=file_info["load_address"],
                    exec_address=file_info["exec_address"],
                    length=len(file_info["data"]),
                    start_sector=next_sector,
                )
            )
            next_sector += sectors_needed

        # Rebuild catalog with new sequential entries
        self._rebuild_catalog(new_entries)

        # Write file data to new sequential sectors
        for file_info, entry in zip(file_data, new_entries):
            # Pad data to sector boundary
            data = file_info["data"]
            padded_length = entry.sectors_required * 256
            padded_data = data + bytes(padded_length - len(data))

            # Write to sectors
            sector_view = self._surface.sector_range(entry.start_sector, entry.sectors_required)
            sector_view[:] = padded_data

        return len(file_data)

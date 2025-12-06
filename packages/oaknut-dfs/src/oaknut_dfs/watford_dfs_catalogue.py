"""Watford DFS catalog implementation."""

from typing import Optional

from oaknut_dfs.catalogue import Catalogue, DiskInfo, FileEntry, ParsedFilename
from oaknut_dfs.surface import Surface


class WatfordDFSCatalogue(Catalogue):
    """Watford DFS catalog - 62 files using dual catalog sections."""

    # Constants
    CATALOGUE_NAME = "watford-dfs"
    MAX_FILES = 62
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 4  # Sectors 0-3
    MAX_FILENAME_LENGTH = 7
    MAX_TITLE_LENGTH = 10  # vs 12 for Acorn DFS (bytes 10-11 reserved)
    VALID_DIRECTORY_CHARS = "$ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(self, surface: Surface):
        super().__init__(surface)

    @classmethod
    def matches(cls, surface: Surface) -> bool:
        """
        Check if surface appears to be Watford DFS format.

        Uses heuristics to identify Watford DFS while excluding
        standard Acorn DFS. Looks for the distinctive 0xAA marker
        in sector 2 and metadata synchronization between sections.

        Returns:
            True if surface appears to be Watford DFS
        """
        # Need at least 4 sectors for Watford DFS
        if surface.num_sectors < 4:
            return False

        # Read all 4 catalog sectors
        sector0 = surface.sector_range(0, 1)
        sector1 = surface.sector_range(1, 1)
        sector2 = surface.sector_range(2, 1)
        sector3 = surface.sector_range(3, 1)

        # Check 1: Validate title chars in sector 0 (bytes 1-9)
        for i in range(1, 10):
            if not cls._is_valid_title_char(sector0[i]):
                return False

        # Check 2: Validate title continuation in sector 1 (bytes 0-3)
        for i in range(4):
            if not cls._is_valid_title_char(sector1[i]):
                return False

        # Check 3: File count validation in section 1
        num_files_byte = sector1[5]
        if num_files_byte & 0x07:  # Bits 0,1,2 must be clear
            return False
        num_files = num_files_byte // 8
        if num_files > 31:  # Each section max 31 files
            return False

        # Check 4: Boot option / sector count byte validation
        boot_sectors_byte = sector1[6]
        if boot_sectors_byte & 0xCC:  # Bits 2,3,6,7 should be clear
            return False

        # Check 5: Total sectors validation
        total_sectors = ((boot_sectors_byte & 0x03) << 8) | sector1[7]
        if total_sectors < 4:  # Minimum sectors
            return False
        if total_sectors % 10 != 0:  # Must be multiple of 10 (sectors per track)
            return False
        if total_sectors > surface.num_sectors:
            return False

        # WATFORD-SPECIFIC: Check for 0xAA marker in sector 2 (first 12 bytes)
        if not all(sector2[i] == 0xAA for i in range(12)):
            return False

        # WATFORD-SPECIFIC: Check sector 3 starts with 4 null bytes
        if not all(sector3[i] == 0x00 for i in range(4)):
            return False

        # WATFORD-SPECIFIC: Verify metadata sync between sections 1 and 3
        if sector3[5] != sector1[5]:  # File count must match
            return False
        if sector3[6] != sector1[6] or sector3[7] != sector1[7]:  # Boot/sectors must match
            return False

        # All checks passed - this is Watford DFS
        return True

    @staticmethod
    def _is_valid_title_char(byte: int) -> bool:
        """
        Check if byte is valid for title character.

        Per DFS spec: no top bit set, and either =0 (padding) or >31 (printable).

        Args:
            byte: Byte value to check

        Returns:
            True if valid title character
        """
        if byte & 0x80:  # Top bit set
            return False
        if byte == 0:  # Null padding is ok
            return True
        if byte <= 31:  # Control characters not ok
            return False
        return True

    def get_disk_info(self) -> DiskInfo:
        """
        Read disk information from catalog.

        Returns metadata from section 1, with file count summed from both sections.

        Returns:
            DiskInfo with title, num_files, total_sectors, boot_option, cycle_number
        """
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Title from sector 0 (bytes 0-9 only - 10 chars max)
        # Bytes 10-11 of sector 0 are reserved for catalog chaining
        title_bytes = bytes(sector0[0:10])
        title = title_bytes.decode('acorn').rstrip()

        # Cycle number (byte 0x104 in sector 1)
        cycle_number = sector1[4]

        # File count from both sections
        section1_files = sector1[5] // 8
        sector3 = self._surface.sector_range(3, 1)
        section2_files = sector3[5] // 8
        num_files = section1_files + section2_files

        # Boot option (bits 4-5 of byte 0x106)
        boot_option = (sector1[6] >> 4) & 0x03

        # Total sectors (10-bit: 2 bits from 0x106 + 8 bits from 0x107)
        total_sectors = ((sector1[6] & 0x03) << 8) | sector1[7]

        return DiskInfo(
            title=title,
            cycle_number=cycle_number,
            num_files=num_files,
            total_sectors=total_sectors,
            boot_option=boot_option
        )

    def list_files(self) -> list[FileEntry]:
        """
        List all files from both catalog sections.

        Returns:
            List of FileEntry objects from sections 1 and 2 combined
        """
        files = []

        # Section 1: Files 1-31 (sectors 0-1)
        files.extend(self._list_files_from_section(0, 1))

        # Section 2: Files 32-62 (sectors 2-3)
        files.extend(self._list_files_from_section(2, 3))

        return files

    def _list_files_from_section(self, sector0_num: int, sector1_num: int) -> list[FileEntry]:
        """
        Read file entries from one catalog section.

        Args:
            sector0_num: First sector of this section (0 or 2)
            sector1_num: Second sector of this section (1 or 3)

        Returns:
            List of FileEntry objects from this section
        """
        sector0 = self._surface.sector_range(sector0_num, 1)
        sector1 = self._surface.sector_range(sector1_num, 1)

        # File count for this section
        num_files_byte = sector1[5]
        num_files = num_files_byte // 8

        entries = []
        for i in range(num_files):
            # File entry layout:
            # Sector 0: offset 0x08 + i*8 = filename (7 bytes) + directory (1 byte)
            # Sector 1: offset 0x08 + i*8 = load_addr_low (2) + exec_addr_low (2) +
            #                                length_low (2) + extra_byte (1) + sector_low (1)

            offset0 = 0x08 + (i * 8)
            offset1 = 0x08 + (i * 8)

            # Parse from sector 0
            filename_bytes = bytes(sector0[offset0:offset0+7])
            filename = filename_bytes.decode('acorn').rstrip()
            directory = chr(sector0[offset0+7] & 0x7F)  # Mask off locked bit
            locked = bool(sector0[offset0+7] & 0x80)

            # Parse from sector 1
            load_low = sector1[offset1] | (sector1[offset1+1] << 8)
            exec_low = sector1[offset1+2] | (sector1[offset1+3] << 8)
            length_low = sector1[offset1+4] | (sector1[offset1+5] << 8)
            extra_byte = sector1[offset1+6]
            sector_low = sector1[offset1+7]

            # Unpack high bits from extra_byte
            # Bits 2-3 of extra_byte = bits 16-17 of load_address
            # Bits 6-7 of extra_byte = bits 16-17 of exec_address
            # Bits 4-5 of extra_byte = bits 16-17 of length
            # Bits 0-1 of extra_byte = bits 8-9 of start_sector
            load_address = load_low | ((extra_byte & 0x0C) << 14)
            exec_address = exec_low | ((extra_byte & 0xC0) << 10)
            length = length_low | ((extra_byte & 0x30) << 12)
            start_sector = sector_low | ((extra_byte & 0x03) << 8)

            entry = FileEntry(
                directory=directory,
                filename=filename,
                locked=locked,
                load_address=load_address,
                exec_address=exec_address,
                length=length,
                start_sector=start_sector
            )
            entries.append(entry)

        return entries

    def add_file_entry(
        self,
        filename: str,
        directory: str,
        load_address: int,
        exec_address: int,
        length: int,
        start_sector: int,
        locked: bool = False
    ) -> None:
        """
        Add file entry to appropriate catalog section.

        Args:
            filename: Filename (max 7 chars)
            directory: Directory letter
            load_address: Load address (18-bit)
            exec_address: Execution address (18-bit)
            length: File length in bytes (18-bit)
            start_sector: Starting sector number (10-bit)
            locked: Whether file is locked

        Raises:
            ValueError: If disk is full (62 files maximum)
        """
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

        # Determine which section to add to
        if disk_info.num_files < 31:
            # Add to section 1 (sectors 0-1)
            self._add_entry_to_section(
                0, 1, disk_info.num_files, filename, directory,
                load_address, exec_address, length, start_sector, locked
            )
        else:
            # Add to section 2 (sectors 2-3)
            # File index within section 2 is (num_files - 31)
            section2_index = disk_info.num_files - 31
            self._add_entry_to_section(
                2, 3, section2_index, filename, directory,
                load_address, exec_address, length, start_sector, locked
            )

        # Sync metadata between sections
        self._sync_metadata()

    def _add_entry_to_section(
        self,
        sector0_num: int,
        sector1_num: int,
        entry_index: int,
        filename: str,
        directory: str,
        load_address: int,
        exec_address: int,
        length: int,
        start_sector: int,
        locked: bool
    ) -> None:
        """Add entry to specific catalog section."""
        sector0 = self._surface.sector_range(sector0_num, 1)
        sector1 = self._surface.sector_range(sector1_num, 1)

        # Calculate entry offset
        entry_offset = 8 + (entry_index * 8)

        # Write filename and directory to sector 0
        filename_padded = filename.ljust(7)
        sector0[entry_offset:entry_offset + 7] = filename_padded.encode("acorn")
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

        # Update file count for this section
        current_count = sector1[5] // 8
        sector1[5] = (current_count + 1) * 8

        # Increment cycle number
        disk_info = self.get_disk_info()
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF

    def _sync_metadata(self) -> None:
        """Ensure metadata is synchronized between both sections."""
        sector1 = self._surface.sector_range(1, 1)
        sector3 = self._surface.sector_range(3, 1)

        # Copy cycle number, boot option, and sector count from section 1 to section 2
        # Note: file counts (byte 5) are NOT synchronized - each section has its own count
        sector3[4] = sector1[4]  # Cycle number
        sector3[6] = sector1[6]  # Boot option + sector count high
        sector3[7] = sector1[7]  # Sector count low

        # Changes to sector3 are persisted automatically (writable memoryview)

    def remove_file_entry(self, filename: str) -> None:
        """
        Remove file entry from catalog.

        Args:
            filename: File to remove

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is locked
        """
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
        """Rebuild both catalog sections from file list."""
        # Get current disk info to preserve title and sector count
        disk_info = self.get_disk_info()

        # Section 1: Files 0-30 (max 31 files)
        section1_files = files[:31]
        self._rebuild_section(0, 1, section1_files, disk_info)

        # Section 2: Files 31-61 (max 31 more files)
        section2_files = files[31:62]
        self._rebuild_section(2, 3, section2_files, disk_info)

        # Sync metadata
        self._sync_metadata()

    def _rebuild_section(
        self,
        sector0_num: int,
        sector1_num: int,
        files: list[FileEntry],
        disk_info: DiskInfo
    ) -> None:
        """Rebuild one catalog section."""
        # Get writable sector views
        sector0 = self._surface.sector_range(sector0_num, 1)
        sector1 = self._surface.sector_range(sector1_num, 1)

        # Clear sectors
        sector0[:] = b'\x00' * 256
        sector1[:] = b'\x00' * 256

        # Write title (or 0xAA marker for section 2)
        if sector0_num == 0:
            # Section 1: write actual title (bytes 0-9 of sector 0)
            title_padded = disk_info.title[:10].ljust(10)
            sector0[0:10] = title_padded.encode("acorn")
            sector0[10:12] = b'\x00\x00'  # Reserved bytes 10-11 for catalog chaining
            # Sector 1 bytes 0-3 not used for title in Watford DFS
        else:
            # Section 2: write 0xAA marker
            sector0[0:12] = b'\xAA' * 12

        # Write file entries
        for i, entry in enumerate(files):
            entry_offset = 8 + (i * 8)

            # Write filename and directory to sector 0
            filename_padded = entry.filename.ljust(7)
            sector0[entry_offset:entry_offset + 7] = filename_padded.encode("acorn")
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

        # Write metadata
        sector1[4] = (disk_info.cycle_number + 1) & 0xFF  # Increment cycle number
        sector1[5] = len(files) * 8  # File count
        sector1[6] = ((disk_info.total_sectors >> 8) & 0x03) | (disk_info.boot_option << 4)
        sector1[7] = disk_info.total_sectors & 0xFF

        # Changes to sectors are persisted automatically (writable memoryviews)

    def find_file(self, filename: str) -> Optional[FileEntry]:
        """
        Find file entry by name.

        Args:
            filename: File to find

        Returns:
            FileEntry if found, None otherwise
        """
        parsed = self.parse_filename(filename)
        all_files = self.list_files()

        for entry in all_files:
            if (entry.filename == parsed.filename and
                entry.directory == parsed.directory):
                return entry
        return None

    def set_title(self, title: str) -> None:
        """
        Set disk title.

        Args:
            title: New title (max 10 chars for Watford DFS)

        Raises:
            ValueError: If title too long or contains invalid characters
        """
        self.validate_title(title)

        # Update section 1 title (bytes 0-9 of sector 0 only)
        # Bytes 10-11 of sector 0 are reserved for catalog chaining
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        title_padded = title[:10].ljust(10)
        sector0[0:10] = title_padded.encode('acorn')

        # Section 2 has 0xAA marker, not title - no update needed

        # Increment cycle number
        sector1[4] = (sector1[4] + 1) & 0xFF

        # Changes to sectors are persisted automatically (writable memoryviews)

    def set_boot_option(self, option: int) -> None:
        """
        Set boot option.

        Args:
            option: Boot option (0-3)

        Raises:
            ValueError: If option not in 0-3 range
        """
        if not 0 <= option <= 3:
            raise ValueError(f"Boot option must be 0-3, got {option}")

        # Update section 1
        sector1 = self._surface.sector_range(1, 1)
        sector1[6] = (sector1[6] & 0x0F) | (option << 4)
        sector1[4] = (sector1[4] + 1) & 0xFF  # Increment cycle number

        # Sync to section 2
        self._sync_metadata()

        # Changes to sectors are persisted automatically (writable memoryviews)

    def lock_file(self, filename: str) -> None:
        """
        Lock file.

        Args:
            filename: File to lock

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        self._set_file_locked(filename, True)

    def unlock_file(self, filename: str) -> None:
        """
        Unlock file.

        Args:
            filename: File to unlock

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        self._set_file_locked(filename, False)

    def _set_file_locked(self, filename: str, locked: bool) -> None:
        """Set locked status for a file."""
        # Find the file
        entry = self.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Find file index in combined list
        files = self.list_files()
        file_index = None
        for i, f in enumerate(files):
            if f.path.upper() == filename.upper():
                file_index = i
                break

        if file_index is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Determine which section the file is in
        if file_index < 31:
            # File is in section 1
            sector0_num = 0
            entry_offset = 8 + (file_index * 8)
        else:
            # File is in section 2
            sector0_num = 2
            entry_offset = 8 + ((file_index - 31) * 8)

        sector0 = self._surface.sector_range(sector0_num, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Modify locked bit (bit 7 of directory byte)
        dir_byte = sector0[entry_offset + 7]
        if locked:
            dir_byte |= 0x80
        else:
            dir_byte &= 0x7F
        sector0[entry_offset + 7] = dir_byte

        # Increment cycle number
        sector1[4] = (sector1[4] + 1) & 0xFF

    def rename_file(self, old_name: str, new_name: str) -> None:
        """
        Rename file.

        Args:
            old_name: Current filename
            new_name: New filename

        Raises:
            FileNotFoundError: If old file doesn't exist
            ValueError: If new filename invalid
        """
        # Find the file
        entry = self.find_file(old_name)
        if entry is None:
            raise FileNotFoundError(f"File not found: {old_name}")

        # Parse and validate new name
        parsed = self.parse_filename(new_name)
        new_filename = parsed.filename
        new_directory = parsed.directory

        # Find file index in combined list
        files = self.list_files()
        file_index = None
        for i, f in enumerate(files):
            if f.path.upper() == old_name.upper():
                file_index = i
                break

        if file_index is None:
            raise FileNotFoundError(f"File not found: {old_name}")

        # Determine which section the file is in
        if file_index < 31:
            # File is in section 1
            sector0_num = 0
            entry_offset = 8 + (file_index * 8)
        else:
            # File is in section 2
            sector0_num = 2
            entry_offset = 8 + ((file_index - 31) * 8)

        sector0 = self._surface.sector_range(sector0_num, 1)
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
        sector1[4] = (sector1[4] + 1) & 0xFF

    def parse_filename(self, path: str) -> ParsedFilename:
        """
        Parse filename path like '$.FILE' or 'A.FILE'.

        Args:
            path: Path string to parse

        Returns:
            ParsedFilename with directory and filename components
        """
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
        """
        Validate filename.

        Args:
            filename: Filename to validate

        Raises:
            ValueError: If filename invalid
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        if len(filename) > self.MAX_FILENAME_LENGTH:
            raise ValueError(
                f"Filename too long: '{filename}' "
                f"(max {self.MAX_FILENAME_LENGTH} chars)"
            )

        # Check for forbidden characters
        forbidden = set('#*:.')
        for i, char in enumerate(filename):
            # Check for forbidden characters
            if char in forbidden:
                raise ValueError(
                    f"Forbidden character '{char}' in filename '{filename}'"
                )

            # '!' is only allowed as the first character
            if char == '!' and i != 0:
                raise ValueError(
                    f"'!' is only allowed as the first character, not at position {i} in '{filename}'"
                )

            # Check for top-bit set characters
            code_point = ord(char)
            if code_point > 127:
                raise ValueError(
                    f"Character '{char}' (code {code_point}) has top bit set in '{filename}'"
                )

            # Check for control characters
            if code_point < 32:
                raise ValueError(
                    f"Control character (code {code_point}) not allowed in '{filename}'"
                )

        # Validate Acorn encoding compatibility
        try:
            filename.encode('acorn')
        except (UnicodeEncodeError, LookupError) as e:
            raise ValueError(f"Filename contains invalid characters: {e}")

    def validate_directory(self, directory: str) -> None:
        """
        Validate directory letter.

        Args:
            directory: Directory to validate

        Raises:
            ValueError: If directory invalid
        """
        if directory.upper() not in self.VALID_DIRECTORY_CHARS:
            raise ValueError(
                f"Invalid directory: {directory!r}. "
                f"Must be one of: {self.VALID_DIRECTORY_CHARS}"
            )

    def validate_title(self, title: str) -> None:
        """
        Validate title.

        Args:
            title: Title to validate

        Raises:
            ValueError: If title invalid
        """
        if len(title) > self.MAX_TITLE_LENGTH:
            raise ValueError(
                f"Title too long: {len(title)} chars "
                f"(max {self.MAX_TITLE_LENGTH} for Watford DFS)"
            )
        # Check valid characters
        for char in title:
            byte = ord(char)
            if not self._is_valid_title_char(byte):
                raise ValueError(f"Invalid title character: {char!r}")

    @property
    def max_files(self) -> int:
        """Maximum files supported."""
        return self.MAX_FILES

    def validate(self) -> list[str]:
        """
        Validate catalog integrity.

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

        # Check for 0xAA marker in sector 2
        sector2 = self._surface.sector_range(2, 1)
        if not all(sector2[i] == 0xAA for i in range(12)):
            errors.append("Missing Watford DFS marker in sector 2")

        # Check metadata sync between sections
        sector1 = self._surface.sector_range(1, 1)
        sector3 = self._surface.sector_range(3, 1)

        # Cycle number should match
        if sector1[4] != sector3[4]:
            errors.append("Cycle number mismatch between catalog sections")

        # Boot option and sector count should match
        if sector1[6] != sector3[6]:
            errors.append("Boot option/sector count mismatch between catalog sections")
        if sector1[7] != sector3[7]:
            errors.append("Sector count mismatch between catalog sections")

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
        Compact disk by removing fragmentation.

        Reads file data from sectors, then rewrites files sequentially
        starting from sector 2 (after catalog sectors 0-3). This consolidates
        free space at the end.

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

        # Build new file entries with sequential sectors starting from sector 4
        # (after 4-sector catalog: sectors 0-3)
        new_entries = []
        next_sector = 4
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

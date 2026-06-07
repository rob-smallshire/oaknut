"""Watford DFS catalog implementation."""

from collections.abc import Sequence
from typing import Optional

from oaknut.dfs.catalogue import (
    DFS_NAME_GRAMMAR,
    Catalogue,
    DiscInfo,
    FileEntry,
    ParsedFilename,
)
from oaknut.dfs.exceptions import CatalogFullError, DFSValidationError
from oaknut.discimage.surface import Surface

_name_key = DFS_NAME_GRAMMAR.name_key


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
    def initialise(
        cls,
        surface: Surface,
        total_sectors: int,
        title: str = "",
        boot_option: int = 0,
    ) -> None:
        """Initialise Watford DFS catalogue on sectors 0–3.

        Section 1 (sectors 0–1): standard catalogue with title.
        Section 2 (sectors 2–3): 0xAA markers + synchronised metadata.
        """
        sectors = surface.sector_range(0, 4)

        # Clear all 4 sectors
        sectors[:] = b"\x00" * 1024

        # --- Section 1 (sectors 0–1) ---

        # Title: first 8 chars in sector 0, next 2 in sector 1 (max 10 for Watford)
        # Bytes 0x10A and 0x10B are reserved for catalogue chaining, leave as zero
        title_padded = title.ljust(10)
        sectors[0x000:0x008] = title_padded[:8].encode("acorn")
        sectors[0x100:0x102] = title_padded[8:10].encode("acorn")

        # Metadata in sector 1
        sectors[0x104] = 0  # Cycle number
        sectors[0x105] = 0  # Number of files × 8 (section 1)
        sectors[0x106] = ((total_sectors >> 8) & 0x03) | (boot_option << 4)
        sectors[0x107] = total_sectors & 0xFF

        # --- Section 2 (sectors 2–3) ---

        # 0xAA marker in the 8-byte title slot of sector 2 (0x200); the file
        # entries that follow at 0x208 must not be clobbered (DiscImage.pdf p9).
        for i in range(8):
            sectors[0x200 + i] = 0xAA

        # Sector 3 bytes 0–3 are null (already zero)

        # Synchronise metadata from section 1 to section 2
        sectors[0x304] = 0  # Section 2's own master sequence number (independent)
        sectors[0x305] = 0  # Number of files × 8 (section 2)
        sectors[0x306] = sectors[0x106]  # Boot option + sector count high
        sectors[0x307] = sectors[0x107]  # Sector count low

    @classmethod
    def match_evidence(cls, surface: Surface) -> list[str] | None:
        """Identification evidence for Watford DFS, or ``None``.

        Looks for the distinctive 8-byte 0xAA marker (0x200) and a
        well-formed two-section extended catalogue, while excluding standard
        Acorn DFS. Each disqualifying check returns ``None``; a match returns
        the verified signals. :meth:`matches` derives from this.
        """
        # Need at least 4 sectors for Watford DFS
        if surface.num_sectors < 4:
            return None

        # Read all 4 catalog sectors
        sector0 = surface.sector_range(0, 1)
        sector1 = surface.sector_range(1, 1)
        sector2 = surface.sector_range(2, 1)
        sector3 = surface.sector_range(3, 1)

        # Check 1: Validate title chars in sector 0 (bytes 1-9)
        for i in range(1, 10):
            if not cls._is_valid_title_char(sector0[i]):
                return None

        # Check 2: Validate title continuation in sector 1 (bytes 0-3)
        for i in range(4):
            if not cls._is_valid_title_char(sector1[i]):
                return None

        # Check 3: File count validation in section 1
        num_files_byte = sector1[5]
        if num_files_byte & 0x07:  # Bits 0,1,2 must be clear
            return None
        num_files = num_files_byte // 8
        if num_files > 31:  # Each section max 31 files
            return None

        # Check 4: Boot option / sector count byte validation
        boot_sectors_byte = sector1[6]
        if boot_sectors_byte & 0xCC:  # Bits 2,3,6,7 should be clear
            return None

        # Check 5: Total sectors validation
        total_sectors = ((boot_sectors_byte & 0x03) << 8) | sector1[7]
        if total_sectors < 4:  # Minimum sectors
            return None
        if total_sectors % 10 != 0:  # Must be multiple of 10 (sectors per track)
            return None
        # A truncated image declares its full size though the file holds only
        # the used sectors; the filing system reads it transparently
        # (issue #1), so a declared total exceeding the surface is accepted.

        # WATFORD-SPECIFIC: 0x200 holds 8 bytes of 0xAA (DiscImage.pdf p9/p11).
        # The marker occupies section 2's 8-byte title slot only; the 31 file
        # entries begin at 0x208, so a populated section 2 overwrites bytes 8+.
        if not all(sector2[i] == 0xAA for i in range(8)):
            return None

        # WATFORD-SPECIFIC: Check sector 3 starts with 4 null bytes
        if not all(sector3[i] == 0x00 for i in range(4)):
            return None

        # WATFORD-SPECIFIC: section 2 carries its OWN file count, independent
        # of section 1 — the two sections hold files 1-31 and 32-62, so a disc
        # with files in just one section has unequal counts. Validate section
        # 2's count byte on its own terms (a count is a multiple of 8, max 31
        # files), never against section 1's.
        section2_count_byte = sector3[5]
        if section2_count_byte & 0x07:  # Bits 0,1,2 must be clear
            return None
        if section2_count_byte // 8 > 31:  # Each section max 31 files
            return None
        # Disc-wide metadata (boot option + total sectors) IS mirrored in both
        # section headers, so those bytes must agree.
        if sector3[6] != sector1[6] or sector3[7] != sector1[7]:
            return None

        # WATFORD-SPECIFIC: the top bits of filename chars 0x005 and 0x006 carry
        # Watford's >256KB extension — length bit 18 and start-sector bit 10
        # (DiscImage.pdf p9). This reader handles only the standard <=256KB
        # layout (18-bit length, 10-bit start sector), so an entry with either
        # bit set is a larger Watford disc whose sizes/sectors we would
        # mis-read: discount it rather than identify it as standard Watford.
        for entries_sector, count_byte in ((sector0, sector1[5]), (sector2, sector3[5])):
            for index in range(count_byte // 8):
                name_offset = 8 + index * 8
                if entries_sector[name_offset + 5] & 0x80:
                    return None
                if entries_sector[name_offset + 6] & 0x80:
                    return None

        # All checks passed — collect the verified signals as evidence.
        total_files = num_files + section2_count_byte // 8
        plural = "" if total_files == 1 else "s"
        return [
            "Watford 0xAA marker at 0x200",
            f"62-file extended catalogue ({total_files} file{plural} across sectors 0–3)",
            "standard layout: no >256 KB extension bits in file entries",
        ]

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

    def get_disc_info(self) -> DiscInfo:
        """
        Read disk information from catalog.

        Returns metadata from section 1, with file count summed from both sections.

        Returns:
            DiscInfo with title, num_files, total_sectors, boot_option, cycle_number
        """
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Watford title is 10 chars: 8 in sector 0 (0x000) + 2 in sector 1
        # (0x100), matching initialise. Sector 0 byte 8 onward is file-entry
        # space, so the title never reaches there.
        title_bytes = bytes(sector0[0:8]) + bytes(sector1[0:2])
        # The fixed-width title field is padded with spaces or NULs; neither
        # is part of the title.
        title = title_bytes.decode("acorn").rstrip(" \x00")

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

        return DiscInfo(
            title=title,
            cycle_number=cycle_number,
            num_files=num_files,
            total_sectors=total_sectors,
            boot_option=boot_option,
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
            filename_bytes = bytes(sector0[offset0 : offset0 + 7])
            filename = filename_bytes.decode("acorn").rstrip()
            directory = chr(sector0[offset0 + 7] & 0x7F)  # Mask off locked bit
            locked = bool(sector0[offset0 + 7] & 0x80)

            # Parse from sector 1
            load_low = sector1[offset1] | (sector1[offset1 + 1] << 8)
            exec_low = sector1[offset1 + 2] | (sector1[offset1 + 3] << 8)
            length_low = sector1[offset1 + 4] | (sector1[offset1 + 5] << 8)
            extra_byte = sector1[offset1 + 6]
            sector_low = sector1[offset1 + 7]

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
                start_sector=start_sector,
            )
            entries.append(entry)

        return entries

    def _add_file_entry_impl(
        self,
        filename: str,
        directory: str,
        load_address: int,
        exec_address: int,
        length: int,
        start_sector: int,
        locked: bool = False,
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
            CatalogFullError: If disk is full (62 files maximum)
        """
        # Validate inputs (case-insensitively); store names as given —
        # DFS preserves case and folds only when matching.
        self.validate_filename(filename)
        self.validate_directory(directory)

        # Read current state
        disc_info = self.get_disc_info()

        if disc_info.num_files >= self.MAX_FILES:
            raise CatalogFullError(f"Catalog full (max {self.MAX_FILES} files)")

        # Determine which section to add to
        if disc_info.num_files < 31:
            # Add to section 1 (sectors 0-1)
            self._add_entry_to_section(
                0,
                1,
                disc_info.num_files,
                filename,
                directory,
                load_address,
                exec_address,
                length,
                start_sector,
                locked,
            )
        else:
            # Add to section 2 (sectors 2-3)
            # File index within section 2 is (num_files - 31)
            section2_index = disc_info.num_files - 31
            self._add_entry_to_section(
                2,
                3,
                section2_index,
                filename,
                directory,
                load_address,
                exec_address,
                length,
                start_sector,
                locked,
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
        locked: bool,
    ) -> None:
        """Add entry to specific catalog section."""
        sector0 = self._surface.sector_range(sector0_num, 1)
        sector1 = self._surface.sector_range(sector1_num, 1)

        # Calculate entry offset
        entry_offset = 8 + (entry_index * 8)

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
            | (((load_address >> 16) & 0x03) << 2)
            | (((length >> 16) & 0x03) << 4)
            | (((exec_address >> 16) & 0x03) << 6)
        )
        sector1[sector1_offset + 6] = extra_byte
        sector1[sector1_offset + 7] = start_sector & 0xFF

        # Update file count for this section
        current_count = sector1[5] // 8
        sector1[5] = (current_count + 1) * 8

        # Increment THIS section's own master sequence number. Each section
        # keeps its own (0x304 is "not a copy of 0x104", DiscImage.pdf p9), so
        # bump the local section's byte, not the disc-wide section-1 value.
        sector1[4] = (sector1[4] + 1) & 0xFF

    def _sync_metadata(self) -> None:
        """Ensure metadata is synchronized between both sections."""
        sector1 = self._surface.sector_range(1, 1)
        sector3 = self._surface.sector_range(3, 1)

        # Mirror only the disc-wide metadata (boot option + total sectors) from
        # section 1 to section 2. The master sequence number (byte 4) and file
        # count (byte 5) are each section's OWN — section 2's 0x304 is "not a
        # copy of 0x104" (DiscImage.pdf p9) — so they are deliberately not
        # synchronised here.
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
        target = _name_key(filename)
        files = [f for f in self.list_files() if _name_key(f.path) != target]

        # Rebuild catalog from scratch
        self._rebuild_catalog(files)

    def _rebuild_catalog(self, files: list[FileEntry]) -> None:
        """Rebuild both catalog sections from file list."""
        # Get current disk info to preserve title and sector count
        disc_info = self.get_disc_info()

        # Section 1: Files 0-30 (max 31 files)
        section1_files = files[:31]
        self._rebuild_section(0, 1, section1_files, disc_info)

        # Section 2: Files 31-61 (max 31 more files)
        section2_files = files[31:62]
        self._rebuild_section(2, 3, section2_files, disc_info)

        # Sync metadata
        self._sync_metadata()

    def _rebuild_section(
        self, sector0_num: int, sector1_num: int, files: list[FileEntry], disc_info: DiscInfo
    ) -> None:
        """Rebuild one catalog section."""
        # Get writable sector views
        sector0 = self._surface.sector_range(sector0_num, 1)
        sector1 = self._surface.sector_range(sector1_num, 1)

        # Clear sectors
        sector0[:] = b"\x00" * 256
        sector1[:] = b"\x00" * 256

        # Write title (or 0xAA marker for section 2)
        if sector0_num == 0:
            # Section 1: write actual title (bytes 0-9 of sector 0)
            title_padded = disc_info.title[:10].ljust(10)
            sector0[0:10] = title_padded.encode("acorn")
            sector0[10:12] = b"\x00\x00"  # Reserved bytes 10-11 for catalog chaining
            # Sector 1 bytes 0-3 not used for title in Watford DFS
        else:
            # Section 2: write 0xAA marker
            sector0[0:12] = b"\xaa" * 12

        # Write file entries
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
                | (((entry.load_address >> 16) & 0x03) << 2)
                | (((entry.length >> 16) & 0x03) << 4)
                | (((entry.exec_address >> 16) & 0x03) << 6)
            )
            sector1[sector1_offset + 6] = extra_byte
            sector1[sector1_offset + 7] = entry.start_sector & 0xFF

        # Write metadata
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF  # Increment cycle number
        sector1[5] = len(files) * 8  # File count
        sector1[6] = ((disc_info.total_sectors >> 8) & 0x03) | (disc_info.boot_option << 4)
        sector1[7] = disc_info.total_sectors & 0xFF

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

        # DFS folds case only when matching, so compare case-insensitively
        # (names are now stored with their original case).
        for entry in all_files:
            if (
                _name_key(entry.filename) == _name_key(parsed.filename)
                and _name_key(entry.directory) == _name_key(parsed.directory)
            ):
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

        # Watford title is 10 chars: 8 in sector 0 (0x000) + 2 in sector 1
        # (0x100). Sector 0 byte 8 onward holds file entries, so the title
        # must not be written there (doing so corrupted the first file).
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        encoded = title[:10].ljust(10).encode("acorn")
        sector0[0:8] = encoded[:8]
        sector1[0:2] = encoded[8:10]

        # Section 2 has 0xAA marker, not title - no update needed

        # Increment section 1's master sequence number (the title lives there).
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
        target = _name_key(filename)
        for i, f in enumerate(files):
            if _name_key(f.path) == target:
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

    def _rename_file_impl(self, old_name: str, new_name: str) -> None:
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
        target = _name_key(old_name)
        for i, f in enumerate(files):
            if _name_key(f.path) == target:
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
        sector0[entry_offset : entry_offset + 7] = new_filename_padded.encode("acorn")

        # Preserve locked bit when setting directory
        dir_byte = ord(new_directory) & 0x7F
        if entry.locked:
            dir_byte |= 0x80
        sector0[entry_offset + 7] = dir_byte

        # Increment cycle number
        sector1[4] = (sector1[4] + 1) & 0xFF

    def _find_file_index(self, filename: str) -> int:
        """Return the catalogue index for *filename*, or raise."""
        files = self.list_files()
        target = _name_key(filename)
        for i, f in enumerate(files):
            if _name_key(f.path) == target:
                return i
        raise FileNotFoundError(f"File not found: {filename}")

    def _section_offset(self, file_index: int) -> tuple[int, int]:
        """Return (sector1_num, entry_offset) for a file index."""
        if file_index < 31:
            return 1, 8 + (file_index * 8)
        else:
            return 3, 8 + ((file_index - 31) * 8)

    def set_load_address(self, filename: str, address: int) -> None:
        """Set load address for a file in the catalogue."""
        file_index = self._find_file_index(filename)
        sector1_num, entry_offset = self._section_offset(file_index)

        sector1 = self._surface.sector_range(sector1_num, 1)

        # Low 16 bits.
        sector1[entry_offset] = address & 0xFF
        sector1[entry_offset + 1] = (address >> 8) & 0xFF

        # High 2 bits in extra byte (bits 2-3), preserve other bits.
        extra_byte = sector1[entry_offset + 6]
        extra_byte = (extra_byte & ~0x0C) | (((address >> 16) & 0x03) << 2)
        sector1[entry_offset + 6] = extra_byte

        # Increment cycle number.
        cycle_sector = self._surface.sector_range(1, 1)
        cycle_sector[4] = (cycle_sector[4] + 1) & 0xFF

    def set_exec_address(self, filename: str, address: int) -> None:
        """Set exec address for a file in the catalogue."""
        file_index = self._find_file_index(filename)
        sector1_num, entry_offset = self._section_offset(file_index)

        sector1 = self._surface.sector_range(sector1_num, 1)

        # Low 16 bits.
        sector1[entry_offset + 2] = address & 0xFF
        sector1[entry_offset + 3] = (address >> 8) & 0xFF

        # High 2 bits in extra byte (bits 6-7), preserve other bits.
        extra_byte = sector1[entry_offset + 6]
        extra_byte = (extra_byte & ~0xC0) | (((address >> 16) & 0x03) << 6)
        sector1[entry_offset + 6] = extra_byte

        # Increment cycle number.
        cycle_sector = self._surface.sector_range(1, 1)
        cycle_sector[4] = (cycle_sector[4] + 1) & 0xFF

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

        # Validate components (case-insensitively); store them as given —
        # DFS preserves case and folds only when matching.
        self.validate_directory(directory)
        self.validate_filename(filename)

        return ParsedFilename(directory=directory, filename=filename)

    def validate_filename(self, filename: str) -> None:
        """Validate that *filename* is storable in a Watford catalogue entry.

        Delegates to the shared :data:`DFS_NAME_GRAMMAR` — Watford and
        Acorn DFS use the same seven-byte, seven-bit name field, so they
        share one liberal rule (see
        :meth:`AcornDFSCatalogue.validate_filename`).
        """
        DFS_NAME_GRAMMAR.validate(filename)

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
                f"Invalid directory: {directory!r}. Must be one of: {self.VALID_DIRECTORY_CHARS}"
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
                f"Title too long: {len(title)} chars (max {self.MAX_TITLE_LENGTH} for Watford DFS)"
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

    def validate(self) -> list["DFSValidationError"]:
        """Validate Watford DFS catalogue integrity.

        Returns a list of :class:`DFSValidationError` instances — empty
        when the catalogue is consistent.
        """
        errors: list[DFSValidationError] = []

        disc_info = self.get_disc_info()
        if disc_info.num_files > self.MAX_FILES:
            errors.append(
                DFSValidationError(f"Too many files: {disc_info.num_files} > {self.MAX_FILES}")
            )

        sector2 = self._surface.sector_range(2, 1)
        # The 0xAA marker is 8 bytes (0x200); 0x208 onward is file entries.
        if not all(sector2[i] == 0xAA for i in range(8)):
            errors.append(DFSValidationError("Missing Watford DFS marker in sector 2"))

        sector1 = self._surface.sector_range(1, 1)
        sector3 = self._surface.sector_range(3, 1)
        # 0x304 is section 2's OWN master sequence number — "not a copy of
        # 0x104" (DiscImage.pdf p9) — so the two sections may legitimately
        # differ; only the boot option and disc size (0x306/7) are mirrored.
        if sector1[6] != sector3[6]:
            errors.append(
                DFSValidationError("Boot option/sector count mismatch between catalog sections")
            )
        if sector1[7] != sector3[7]:
            errors.append(DFSValidationError("Sector count mismatch between catalog sections"))

        files = self.list_files()
        sector_map: dict[int, str] = {}
        for entry in files:
            for sector in range(entry.start_sector, entry.start_sector + entry.sectors_required):
                if sector in sector_map:
                    errors.append(
                        DFSValidationError(
                            f"Sector {sector} used by both {sector_map[sector]} and {entry.path}"
                        )
                    )
                else:
                    sector_map[sector] = entry.path

        total_sectors = self._surface.num_sectors
        for entry in files:
            end_sector = entry.start_sector + entry.sectors_required
            if end_sector > total_sectors:
                errors.append(
                    DFSValidationError(
                        f"File {entry.path} extends beyond disk: "
                        f"sector {end_sector} > {total_sectors}"
                    )
                )

        names = [_name_key(f.path) for f in files]
        duplicates = [name for name in set(names) if names.count(name) > 1]
        if duplicates:
            errors.append(DFSValidationError(f"Duplicate filenames: {', '.join(duplicates)}"))

        return errors

    def compact(self, *, order: Sequence[str] = ()) -> int:
        """
        Compact disk by removing fragmentation.

        Reads file data from sectors, then rewrites files sequentially
        starting from sector 2 (after catalog sectors 0-3). This consolidates
        free space at the end.

        *order* is a partial list of paths to lay down first, in the lowest
        sectors; unlisted files follow in their current order. The lock bit
        is logical delete protection, not a placement constraint, so locked
        files are relocated like any other and stay locked.

        Returns:
            Number of files compacted

        Raises:
            FileNotFoundError: If *order* names a file not on the disc
        """
        files = self.list_files()

        if not files:
            return 0

        # Lay files down in physical order so a plain compaction preserves
        # their relative positions; an explicit order promotes the named
        # files ahead of the rest.
        files = sorted(files, key=lambda f: f.start_sector)
        if order:
            files = self._ordered_files(files, order)

        # Read all file data from sectors (with metadata)
        file_data = []
        for entry in files:
            # Read the actual sectors containing file data
            sectors_view = self._surface.sector_range(entry.start_sector, entry.sectors_required)
            # Copy only the actual file data (trim padding)
            data = bytes(sectors_view[: entry.length])
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

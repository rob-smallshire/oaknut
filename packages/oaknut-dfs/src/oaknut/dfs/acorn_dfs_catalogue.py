"""Acorn DFS catalog implementation."""

from collections.abc import Sequence

from oaknut.dfs.catalogue import Catalogue, DiscInfo, FileEntry, ParsedFilename
from oaknut.dfs.exceptions import CatalogFullError, DFSValidationError
from oaknut.discimage.surface import Surface


class AcornDFSCatalogue(Catalogue):
    """Acorn DFS catalog implementation (sectors 0-1, max 31 files)."""

    # Constants
    CATALOGUE_NAME = "acorn-dfs"
    MAX_FILES = 31
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 2
    MAX_FILENAME_LENGTH = 7
    MAX_TITLE_LENGTH = 12
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
        """Initialise Acorn DFS catalogue on sectors 0–1."""
        sector0 = surface.sector_range(0, 1)
        sector1 = surface.sector_range(1, 1)

        # Clear both sectors
        sector0[:] = b"\x00" * 256
        sector1[:] = b"\x00" * 256

        # Title: first 8 chars in sector 0, next 4 in sector 1
        title_padded = title.ljust(12)
        sector0[0:8] = title_padded[:8].encode("acorn")
        sector1[0:4] = title_padded[8:12].encode("acorn")

        # Metadata in sector 1
        sector1[4] = 0  # Cycle number
        sector1[5] = 0  # Number of files × 8
        sector1[6] = ((total_sectors >> 8) & 0x03) | (boot_option << 4)
        sector1[7] = total_sectors & 0xFF

    @classmethod
    def match_evidence(cls, surface: Surface) -> list[str] | None:
        """Identification evidence for standard Acorn DFS, or ``None``.

        Uses the heuristics from "Guide to Disc Formats.pdf" to identify
        Acorn DFS while excluding Watford DFS and other variants. Each
        disqualifying check returns ``None``; a well-formed catalogue
        returns the verified signals. :meth:`matches` derives from this.
        """
        # Need at least 4 sectors to check for Watford DFS markers
        if surface.num_sectors < 4:
            return None

        # Read catalogue sectors
        sector0 = surface.sector_range(0, 1)
        sector1 = surface.sector_range(1, 1)

        # Check 1: Offset 0x001 - 9 bytes of title without top bit set and >31 or =0
        for i in range(1, 10):
            if not cls._is_valid_title_char(sector0[i]):
                return None

        # Check 2: Offset 0x100 - 4 bytes of title without top bit set and >31 or =0
        for i in range(4):
            if not cls._is_valid_title_char(sector1[i]):
                return None

        # Check 3: Offset 0x105 - bits 0,1,2 should be clear (multiple of 8)
        num_files_byte = sector1[5]
        if num_files_byte & 0x07:  # Bits 0,1,2 set
            return None
        num_files = num_files_byte // 8
        if num_files > cls.MAX_FILES:  # Should be <= 31 for Acorn DFS
            return None

        # Check 4: Offset 0x106 - bits 2,3,6,7 should be clear
        boot_sectors_byte = sector1[6]
        if boot_sectors_byte & 0xCC:  # Bits 2,3,6,7 set
            return None

        # Check 5: Total sectors calculation and divisibility by 10
        total_sectors = ((boot_sectors_byte & 0x03) << 8) | sector1[7]
        if total_sectors < 4:  # Minimum sectors
            return None
        if total_sectors % 10 != 0:
            return None

        # Check 6 (optional): Tracks should be reasonable
        # PDF notes: "not all double-sided discs have the same number of tracks"
        # and "there are valid DFS discs that have other numbers of tracks"
        # So we keep this check very lenient - just ensure it's positive
        tracks = total_sectors // 10
        if tracks < 1:
            return None

        # A truncated image declares its full (untruncated) sector count
        # while the file holds only the used sectors; the filing system
        # reads it transparently (issue #1), so a declared total that
        # exceeds the surface is *accepted*, not rejected — checks 1–6
        # already establish a well-formed catalogue.

        # EXCLUSION CHECK: Must NOT be Watford DFS
        # Watford DFS has specific markers in sectors 2-3
        sector2 = surface.sector_range(2, 1)
        sector3 = surface.sector_range(3, 1)

        # If sector 2 starts with 8 bytes of 0xAA, it's Watford
        if all(sector2[i] == 0xAA for i in range(8)):
            return None

        # If sector 3 starts with 4 bytes of 0x00 AND has matching boot/sectors
        # then it's Watford
        if (
            all(sector3[i] == 0x00 for i in range(4))
            and sector3[5] & 0x07 == 0  # bits 0,1,2 clear
            and sector3[6] == sector1[6]  # matches boot/sectors high
            and sector3[7] == sector1[7]
        ):  # matches sectors low
            return None

        # All checks passed - this is standard Acorn DFS.
        plural = "" if num_files == 1 else "s"
        return [f"well-formed Acorn DFS catalogue ({num_files} file{plural} in sectors 0–1)"]

    @staticmethod
    def _is_valid_title_char(byte: int) -> bool:
        """
        Check if byte is valid for title character.

        Per PDF: no top bit set, and either =0 (padding) or >31 (printable).

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

    @property
    def max_files(self) -> int:
        return self.MAX_FILES

    def get_disc_info(self) -> DiscInfo:
        """Read disk info from sectors 0-1."""
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Parse title (8 bytes from sector 0 + 4 bytes from sector 1)
        title_part1 = bytes(sector0[0:8]).decode("acorn")
        title_part2 = bytes(sector1[0:4]).decode("acorn")
        # The fixed-width title field is padded with spaces or NULs; neither
        # is part of the title.
        title = (title_part1 + title_part2).rstrip(" \x00")

        # Parse metadata from sector 1
        cycle_number = sector1[4]
        num_files = sector1[5] // 8  # Last entry byte / 8
        extra_byte = sector1[6]
        sector_count_low = sector1[7]

        total_sectors = sector_count_low | ((extra_byte & 0x03) << 8)
        boot_option = (extra_byte >> 4) & 0x03

        return DiscInfo(
            title=title,
            cycle_number=cycle_number,
            num_files=num_files,
            total_sectors=total_sectors,
            boot_option=boot_option,
        )

    def list_files(self) -> list[FileEntry]:
        """List all files from catalog sectors 0-1."""
        disc_info = self.get_disc_info()
        if disc_info.num_files == 0:
            return []

        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        files = []
        for i in range(disc_info.num_files):
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
        """
        Validate that *filename* is storable in a DFS catalogue entry.

        The check is deliberately liberal: it forbids only what the
        seven-byte name field cannot represent, not what the command
        line finds awkward to type. So ``#`` and ``*`` (wildcards) and a
        non-leading ``!`` are *allowed* — real discs store them (Guardian
        ships ``GUARD#1`` / ``GUARD#2``), and selecting them by wildcard
        versus literal is a concern for the matching layer, not storage.

        Forbidden:
        - ``:`` and ``.`` — drive and directory separators; a name
          carrying one cannot be addressed through the dotted-path
          syntax yet (escaping is a separate, later concern).
        - Top-bit-set characters (>127) and control characters (<32) —
          outside the seven-bit name field.
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        if len(filename) > self.MAX_FILENAME_LENGTH:
            raise ValueError(
                f"Filename too long: '{filename}' (max {self.MAX_FILENAME_LENGTH} chars)"
            )

        # Only the path separators are unstorable through the path
        # syntax; wildcard metacharacters (# *) and ! are valid name bytes.
        forbidden = set(":.")
        for char in filename:
            if char in forbidden:
                raise ValueError(f"Forbidden character '{char}' in filename '{filename}'")

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
            filename.encode("acorn")
        except (UnicodeEncodeError, LookupError) as e:
            raise ValueError(f"Filename contains invalid characters: {e}")

    def validate_directory(self, directory: str) -> None:
        """Validate Acorn DFS directory character."""
        if len(directory) != 1:
            raise ValueError(f"Directory must be single character, got: '{directory}'")

        if directory.upper() not in self.VALID_DIRECTORY_CHARS:
            raise ValueError(f"Invalid directory '{directory}'. Must be $ or A-Z")

    def validate_title(self, title: str) -> None:
        """
        Validate Acorn DFS title constraints.

        Per "Guide to Disc Formats.pdf", title characters must:
        - Not have top bit set (must be <= 127)
        - Not be control characters (< 32), except null (0) for padding
        """
        if len(title) > self.MAX_TITLE_LENGTH:
            raise ValueError(f"Title too long: '{title}' (max {self.MAX_TITLE_LENGTH} chars)")

        # Check each character
        for i, char in enumerate(title):
            code_point = ord(char)

            # Check for top-bit set characters
            if code_point > 127:
                raise ValueError(
                    f"Title character '{char}' at position {i} has top bit set (code {code_point})"
                )

            # Check for control characters (except null/space for padding)
            if code_point < 32 and code_point != 0:
                raise ValueError(
                    f"Title contains control character at position {i} (code {code_point})"
                )

        # Validate Acorn encoding compatibility
        try:
            title.encode("acorn")
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
        disc_info = self.get_disc_info()

        if disc_info.num_files >= self.MAX_FILES:
            raise CatalogFullError(f"Catalog full (max {self.MAX_FILES} files)")

        # Rebuild the catalogue with the new entry folded in. The rebuild
        # owns slot order (descending start sector) and the bit packing, so
        # add and remove cannot drift apart.
        new_entry = FileEntry(
            filename=filename,
            directory=directory,
            locked=locked,
            load_address=load_address,
            exec_address=exec_address,
            length=length,
            start_sector=start_sector,
        )
        self._rebuild_catalog([*self.list_files(), new_entry])

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
        """Rebuild catalog sectors from file list.

        Entries are stored in descending start-sector order, the
        convention a real Acorn DFS keeps: the file in the highest sectors
        is the first catalogue entry, the one in the lowest (often
        ``!BOOT``) the last. The caller's ordering of *files* does not
        matter — physical position alone fixes the slot order.
        """
        # Clear catalog sectors
        sector0 = self._surface.sector_range(0, 1)
        sector1 = self._surface.sector_range(1, 1)

        # Get current disk info to preserve title and sector count
        disc_info = self.get_disc_info()

        # Clear everything
        sector0[:] = b"\x00" * 256
        sector1[:] = b"\x00" * 256

        # Restore title
        title_part1 = disc_info.title[:8].ljust(8)
        title_part2 = disc_info.title[8:12].ljust(4)
        sector0[0:8] = title_part1.encode("acorn")
        sector1[0:4] = title_part2.encode("acorn")

        # Write each file entry, highest start sector first.
        for i, entry in enumerate(sorted(files, key=lambda f: f.start_sector, reverse=True)):
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

        # Update metadata
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF  # Increment cycle number
        sector1[5] = len(files) * 8  # Number of files
        sector1[6] = ((disc_info.total_sectors >> 8) & 0x03) | (
            disc_info.boot_option << 4
        )  # Extra byte
        sector1[7] = disc_info.total_sectors & 0xFF  # Sector count low

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
        disc_info = self.get_disc_info()
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF

    def set_boot_option(self, option: int) -> None:
        """Set boot option (0-3)."""
        if not 0 <= option <= 3:
            raise ValueError(f"Boot option must be 0-3, got {option}")

        sector1 = self._surface.sector_range(1, 1)
        disc_info = self.get_disc_info()

        # Update boot option in extra byte (bits 4-5)
        extra_byte = sector1[6]
        extra_byte = (extra_byte & 0xCF) | (option << 4)
        sector1[6] = extra_byte

        # Increment cycle number
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF

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
        disc_info = self.get_disc_info()
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF

    def _find_file_index(self, filename: str) -> int:
        """Return the catalogue index for *filename*, or raise."""
        files = self.list_files()
        for i, f in enumerate(files):
            if f.path.upper() == filename.upper():
                return i
        raise FileNotFoundError(f"File not found: {filename}")

    def set_load_address(self, filename: str, address: int) -> None:
        """Set load address for a file in the catalogue."""
        file_index = self._find_file_index(filename)
        entry_offset = 8 + (file_index * 8)

        sector1 = self._surface.sector_range(1, 1)
        sector1_offset = entry_offset

        # Low 16 bits.
        sector1[sector1_offset] = address & 0xFF
        sector1[sector1_offset + 1] = (address >> 8) & 0xFF

        # High 2 bits in extra byte (bits 2-3), preserve other bits.
        extra_byte = sector1[sector1_offset + 6]
        extra_byte = (extra_byte & ~0x0C) | (((address >> 16) & 0x03) << 2)
        sector1[sector1_offset + 6] = extra_byte

        # Increment cycle number.
        disc_info = self.get_disc_info()
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF

    def set_exec_address(self, filename: str, address: int) -> None:
        """Set exec address for a file in the catalogue."""
        file_index = self._find_file_index(filename)
        entry_offset = 8 + (file_index * 8)

        sector1 = self._surface.sector_range(1, 1)
        sector1_offset = entry_offset

        # Low 16 bits.
        sector1[sector1_offset + 2] = address & 0xFF
        sector1[sector1_offset + 3] = (address >> 8) & 0xFF

        # High 2 bits in extra byte (bits 6-7), preserve other bits.
        extra_byte = sector1[sector1_offset + 6]
        extra_byte = (extra_byte & ~0xC0) | (((address >> 16) & 0x03) << 6)
        sector1[sector1_offset + 6] = extra_byte

        # Increment cycle number.
        disc_info = self.get_disc_info()
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF

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
        sector0[entry_offset : entry_offset + 7] = new_filename_padded.encode("acorn")

        # Preserve locked bit when setting directory
        dir_byte = ord(new_directory) & 0x7F
        if entry.locked:
            dir_byte |= 0x80
        sector0[entry_offset + 7] = dir_byte

        # Increment cycle number
        disc_info = self.get_disc_info()
        sector1[4] = (disc_info.cycle_number + 1) & 0xFF

    def validate(self) -> list["DFSValidationError"]:
        """Validate Acorn DFS catalogue integrity.

        Returns a list of :class:`DFSValidationError` instances — empty
        when the catalogue is consistent. Callers iterate the list to
        present every defect rather than aborting on the first.
        """
        errors: list[DFSValidationError] = []

        disc_info = self.get_disc_info()
        if disc_info.num_files > self.MAX_FILES:
            errors.append(
                DFSValidationError(f"Too many files: {disc_info.num_files} > {self.MAX_FILES}")
            )

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

        names = [f.path.upper() for f in files]
        duplicates = [name for name in set(names) if names.count(name) > 1]
        if duplicates:
            errors.append(DFSValidationError(f"Duplicate filenames: {', '.join(duplicates)}"))

        return errors

    def compact(self, *, order: Sequence[str] = ()) -> int:
        """
        Compact Acorn DFS catalogue by removing fragmentation.

        Reads file data from sectors, then rewrites files sequentially
        starting from sector 2. This consolidates free space at the end.

        *order* is a partial list of paths to lay down first, in the lowest
        sectors (in the given order); unlisted files follow in their current
        order. It lets a caller put boot/loader files where they load
        fastest. An empty order keeps the existing order.

        The lock bit is logical delete/overwrite protection, not a
        constraint on physical placement, so locked files are relocated
        like any other and stay locked.

        Returns:
            Number of files compacted

        Raises:
            FileNotFoundError: If *order* names a file not on the disc
        """
        files = self.list_files()

        if not files:
            return 0

        # Lay files down in physical order so a plain compaction preserves
        # their relative positions (the stored catalogue is descending, so
        # its own order must not drive the lay-down). An explicit order then
        # promotes the named files ahead of the rest.
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

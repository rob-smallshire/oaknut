"""Acorn DFS catalog implementation."""

from collections.abc import Sequence

from oaknut.dfs.catalogue import (
    COMMAND_DIRECTORY_CHARS,
    DFS_NAME_GRAMMAR,
    Catalogue,
    DiscInfo,
    FileEntry,
    Mismatch,
    ParsedFilename,
    check_command_directory,
    check_stored_directory,
    expand_host_address,
)
from oaknut.dfs.exceptions import (
    CatalogFullError,
    DFSValidationError,
    FileLocked,
    MalformedSectorCountError,
)
from oaknut.discimage import BYTES_PER_SECTOR
from oaknut.discimage.surface import Surface
from oaknut.filesystem import InvalidTitleError

_name_key = DFS_NAME_GRAMMAR.name_key


#: Bits of sector 1 byte 6 that hold no Acorn DFS field. Bits 2–3 extend
#: the sector count on other DFSes (Opus DDOS's 11-bit count), so a disc
#: carrying them is malformed rather than foreign; bits 6–7 disqualify.
_SECTOR_COUNT_EXTENSION_BITS = 0x0C
_FOREIGN_BITS = 0xC0


def _file_extent(sector1: Sequence[int]) -> int:
    """The first sector past the last file, or 2 (past the catalogue) with none."""
    extent = 2
    for i in range(sector1[5] // 8):
        offset = 8 + i * 8
        extra = sector1[offset + 6]
        length = sector1[offset + 4] | (sector1[offset + 5] << 8) | ((extra & 0x30) << 12)
        start = sector1[offset + 7] | ((extra & 0x03) << 8)
        extent = max(extent, start + (length + BYTES_PER_SECTOR - 1) // BYTES_PER_SECTOR)
    return extent


def sector_count_defect(
    sector1: Sequence[int], *, side_sectors: int | None = None
) -> MalformedSectorCountError | None:
    """The finding for a malformed sector-count field, or ``None`` if it is sound.

    The single analysis of the field (sector 1 bytes 6–7): recognition
    treats a finding as a soft signal, sizing falls back to the side's
    true size, and validation reports it. The field is malformed when a
    reserved bit of &106 extends it, when it is not a positive multiple
    of ten, or when files run past it. A declared count *larger* than the
    image is sound: a truncated image keeps its full disc's count.
    *side_sectors*, the side's true size when known, is named in the
    finding.
    """
    byte6, low = sector1[6], sector1[7]
    extension = byte6 & _SECTOR_COUNT_EXTENSION_BITS
    declared = (((byte6 & 0x0F) if extension else (byte6 & 0x03)) << 8) | low
    extent = _file_extent(sector1)
    if extension:
        cause = MalformedSectorCountError.EXTENSION_BITS
        problem = f"reserved bits &{extension:02X} of &106 are set"
    elif declared < 10 or declared % 10:
        cause = MalformedSectorCountError.IMPLAUSIBLE
        problem = "that is not a positive multiple of ten"
    elif declared < extent and (side_sectors is None or declared < side_sectors):
        # Files running past a count that already covers the whole side
        # are the files' defect (validated separately), not the count's.
        cause = MalformedSectorCountError.FILES_RUN_PAST
        problem = f"files run to sector {extent}"
    else:
        return None
    holds = f"; the side holds {side_sectors}" if side_sectors is not None else ""
    return MalformedSectorCountError(
        f"catalogue declares {declared} sectors (&{byte6:02X}{low:02X} at &106), "
        f"but {problem}{holds}",
        cause=cause,
        declared=declared,
        side_sectors=side_sectors,
    )


class AcornDFSCatalogue(Catalogue):
    """Acorn DFS catalog implementation (sectors 0-1, max 31 files)."""

    # Constants
    CATALOGUE_NAME = "acorn-dfs"
    MAX_FILES = 31
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 2
    MAX_FILENAME_LENGTH = 7
    MAX_TITLE_LENGTH = 12
    VALID_DIRECTORY_CHARS = COMMAND_DIRECTORY_CHARS

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
    def assess(cls, surface: Surface) -> list[str] | Mismatch:
        """Identification evidence for standard Acorn DFS, or why not.

        Uses the heuristics from "Guide to Disc Formats.pdf" to identify
        Acorn DFS while excluding Watford DFS and other variants. Each
        disqualifying check returns a :class:`Mismatch` naming the field
        and its value; a well-formed catalogue returns the verified
        signals. :meth:`match_evidence` and :meth:`matches` derive from this.
        """
        # The Acorn catalogue is sectors 0-1, so two sectors is the
        # minimum — a blank disc truncated to just its catalogue is a
        # legitimate (truncated) Acorn DFS image. The Watford-exclusion
        # check below needs sectors 2-3 and so runs only when present;
        # with fewer than four sectors the image cannot be Watford anyway
        # (its extended catalogue lives there), so nothing is lost.
        if surface.num_sectors < 2:
            return Mismatch(
                f"image too small for a DFS catalogue: {surface.num_sectors} sector(s), needs 2"
            )

        # Read catalogue sectors
        sector0 = surface.sector_range(0, 1)
        sector1 = surface.sector_range(1, 1)

        # Checks 1 & 2: the 12-byte title (nine bytes from sector 0,
        # offset 0x001, plus four from sector 1, offset 0x100). The title
        # is 7-bit ASCII, so a top-bit-set byte is not DFS and disqualifies
        # outright. A control character (byte <= 31) is unconventional but
        # real — a commercial disc such as Oxford Pascal embeds a
        # decorative form-feed, CR and LF — so it does not disqualify on
        # its own; instead it falls back to corroborating the catalogue
        # against the real surface (Check 5b), like an implausible total.
        soft_signals: list[str] = []
        title_bytes = [(i, sector0[i]) for i in range(1, 10)]
        title_bytes += [(0x100 + i, sector1[i]) for i in range(4)]
        for offset, byte in title_bytes:
            kind = cls._title_char_kind(byte)
            if kind == "reject":
                return Mismatch(
                    f"catalogue title byte &{byte:02X} at &{offset:03X} has its top bit set"
                )
            if kind == "control" and not soft_signals:
                soft_signals.append(
                    f"title byte &{byte:02X} at &{offset:03X} is a control character"
                )

        # Check 3: Offset 0x105 - bits 0,1,2 should be clear (multiple of 8)
        num_files_byte = sector1[5]
        if num_files_byte & 0x07:  # Bits 0,1,2 set
            return Mismatch(f"file count byte &{num_files_byte:02X} at &105 is not a multiple of 8")
        num_files = num_files_byte // 8

        # Check 4: Offset 0x106 - bits 6,7 hold no field on any DFS.
        boot_sectors_byte = sector1[6]
        if boot_sectors_byte & _FOREIGN_BITS:
            return Mismatch(
                f"boot option byte &{boot_sectors_byte:02X} at &106 has reserved bits set "
                f"(&{boot_sectors_byte & _FOREIGN_BITS:02X})"
            )

        # Check 5: the sector-count field. Writers stamp malformed counts on
        # otherwise well-formed catalogues — Owlet (bbcmicrobot.com) writes
        # 3; the PanOS 1.40 installation discs set bit 2 of &106 (Opus's
        # 11-bit form) to declare 1600 — so a malformed count is not
        # trustworthy enough to disqualify on its own. It falls back to
        # corroborating the catalogue against the real surface (Check 5b).
        defect = sector_count_defect(sector1)
        if defect is not None and defect.doubts_the_catalogue:
            soft_signals.append(str(defect))

        # Check 5b: when a soft signal is off — an implausible declared
        # total or a control character in the title — the file table must
        # be internally consistent with the actual surface: at least one
        # file, every entry living in the data area (sector >= 2) and
        # ending within the surface. Random data almost never satisfies
        # this on top of the count/flag/7-bit checks already passed.
        if soft_signals:
            misfit = cls._file_table_misfit(surface, sector1, num_files)
            if misfit is not None:
                return Mismatch(f"{'; '.join(soft_signals)}, and {misfit}")

        # A truncated image declares its full (untruncated) sector count
        # while the file holds only the used sectors; the filing system
        # reads it transparently (issue #1), so a declared total that
        # exceeds the surface is *accepted*, not rejected — the checks
        # above already establish a well-formed catalogue.

        # EXCLUSION CHECK: Must NOT be Watford DFS. Watford's markers live
        # in sectors 2-3, so this only applies when the image actually has
        # them; a two- or three-sector image cannot be Watford (its
        # extended catalogue would be missing), so it is left to Acorn.
        if surface.num_sectors >= 4:
            sector2 = surface.sector_range(2, 1)
            sector3 = surface.sector_range(3, 1)

            # If sector 2 starts with 8 bytes of 0xAA, it's Watford
            if all(sector2[i] == 0xAA for i in range(8)):
                return Mismatch("sector 2 carries the Watford DFS marker (eight &AA bytes)")

            # If sector 3 starts with 4 bytes of 0x00 AND has matching
            # boot/sectors then it's Watford
            if (
                all(sector3[i] == 0x00 for i in range(4))
                and sector3[5] & 0x07 == 0  # bits 0,1,2 clear
                and sector3[6] == sector1[6]  # matches boot/sectors high
                and sector3[7] == sector1[7]
            ):  # matches sectors low
                return Mismatch("sector 3 carries a Watford DFS second catalogue section")

        # All checks passed - this is standard Acorn DFS.
        plural = "" if num_files == 1 else "s"
        evidence = [f"well-formed Acorn DFS catalogue ({num_files} file{plural} in sectors 0–1)"]
        if defect is not None:
            evidence.append(f"malformed sector count: {defect}")
        return evidence

    @staticmethod
    def _title_char_kind(byte: int) -> str:
        """Classify a title byte as ``"clean"``, ``"control"`` or ``"reject"``.

        The title is 7-bit ASCII. A top-bit-set byte is not DFS and
        ``"reject"``\\ s the catalogue. ``0`` (NUL padding) and printable
        bytes (>= 32) are ``"clean"``. A control character (1–31) is
        ``"control"``: tolerated, but only with file-table corroboration,
        since a decorative control character in a real title is rare and
        also resembles garbage.
        """
        if byte & 0x80:  # Top bit set — not 7-bit ASCII, not DFS.
            return "reject"
        if byte == 0 or byte > 31:  # NUL padding or printable.
            return "clean"
        return "control"

    @staticmethod
    def _file_table_misfit(surface: Surface, sector1: Sequence[int], num_files: int) -> str | None:
        """Why the catalogue entries do not fit the actual surface, or ``None``.

        Used to corroborate a catalogue whose self-declared total-sector
        count is implausible: each of *num_files* entries must start in
        the data area (sector >= 2, after the catalogue) and end at or
        before the surface's true sector count. With no files there is
        nothing to corroborate, so an empty table does not vouch for the
        catalogue.
        """
        if num_files == 0:
            return "there are no files to corroborate the catalogue"
        for i in range(num_files):
            entry_offset = 8 + (i * 8)
            extra_byte = sector1[entry_offset + 6]
            length = (
                sector1[entry_offset + 4]
                | (sector1[entry_offset + 5] << 8)
                | ((extra_byte & 0x30) << 12)
            )
            start_sector = sector1[entry_offset + 7] | ((extra_byte & 0x03) << 8)
            length_sectors = (length + BYTES_PER_SECTOR - 1) // BYTES_PER_SECTOR
            if start_sector < 2:
                return f"file {i + 1} starts in sector {start_sector}, inside the catalogue"
            if start_sector + length_sectors > surface.num_sectors:
                return (
                    f"file {i + 1} runs to sector {start_sector + length_sectors}, "
                    f"past the image's {surface.num_sectors}"
                )
        return None

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
        # A malformed count does not describe the side; size it by the
        # surface, which a rewrite of the catalogue then records.
        if sector_count_defect(sector1, side_sectors=self._surface.num_sectors) is not None:
            total_sectors = self._surface.num_sectors
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
            load_address = expand_host_address(load_low | ((extra_byte & 0x0C) << 14))
            exec_address = expand_host_address(exec_low | ((extra_byte & 0xC0) << 10))
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

    def parse_filename(self, path: str, *, verbatim: bool = False) -> ParsedFilename:
        """Parse and validate an Acorn DFS filename, preserving its case.

        DFS stores a name verbatim and folds case only when matching, so
        the parsed components keep the caller's case; validation is
        case-insensitive (a lower-case directory letter is accepted).
        """
        # Parse using base class helper
        directory, filename = self._default_parse_filename(path, default_directory="$")

        # Validate components (case-insensitively); store them as given.
        if verbatim:
            check_stored_directory(directory)
        else:
            self.validate_directory(directory)
        self.validate_filename(filename)

        return ParsedFilename(directory=directory, filename=filename)

    def validate_filename(self, filename: str) -> None:
        """Validate that *filename* is storable in a DFS catalogue entry.

        Delegates to the shared :data:`DFS_NAME_GRAMMAR`, the single
        source of truth for the seven-byte name field's storage rules
        (also reported by ``disc describe-filesystem``). Deliberately
        liberal: ``#`` and ``*`` (wildcards) and a non-leading ``!`` are
        valid name bytes — only the ``:`` / ``.`` separators and bytes
        outside the seven-bit field are refused.
        """
        DFS_NAME_GRAMMAR.validate(filename)

    def validate_directory(self, directory: str) -> None:
        """Validate a new name's directory: one DFS commands can create."""
        check_command_directory(directory)

    @classmethod
    def validate_title(cls, title: str) -> None:
        """
        Validate Acorn DFS title constraints.

        Per "Guide to Disc Formats.pdf", title characters must:
        - Not have top bit set (must be <= 127)
        - Not be control characters (< 32), except null (0) for padding
        """
        if len(title) > cls.MAX_TITLE_LENGTH:
            raise InvalidTitleError(f"Title too long: '{title}' (max {cls.MAX_TITLE_LENGTH} chars)")

        # Check each character
        for i, char in enumerate(title):
            code_point = ord(char)

            # Check for top-bit set characters
            if code_point > 127:
                raise InvalidTitleError(
                    f"Title character '{char}' at position {i} has top bit set (code {code_point})"
                )

            # Check for control characters (except null/space for padding)
            if code_point < 32 and code_point != 0:
                raise InvalidTitleError(
                    f"Title contains control character at position {i} (code {code_point})"
                )

        # Validate Acorn encoding compatibility
        try:
            title.encode("acorn")
        except (UnicodeEncodeError, LookupError) as e:
            raise InvalidTitleError(f"Title contains invalid characters: {e}") from None

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
        """Add file entry to catalog, increment cycle number."""
        # Validate inputs (case-insensitively); store names as given —
        # DFS preserves case and folds only when matching.
        self.validate_filename(filename)
        check_stored_directory(directory)

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
            raise FileLocked(f"File is locked: {filename}")

        # Get all files except the one to remove
        target = _name_key(filename)
        files = [f for f in self.list_files() if _name_key(f.path) != target]

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
        target = _name_key(filename)
        for i, f in enumerate(files):
            if _name_key(f.path) == target:
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
        target = _name_key(filename)
        for i, f in enumerate(files):
            if _name_key(f.path) == target:
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

    def _rename_file_impl(self, old_name: str, new_name: str) -> None:
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
        target = _name_key(old_name)
        for i, f in enumerate(files):
            if _name_key(f.path) == target:
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

        defect = sector_count_defect(
            self._surface.sector_range(1, 1), side_sectors=self._surface.num_sectors
        )
        if defect is not None:
            errors.append(defect)

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

        names = [_name_key(f.path) for f in files]
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

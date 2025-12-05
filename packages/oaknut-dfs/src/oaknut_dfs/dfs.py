"""High-level DFS filesystem operations."""

from typing import Optional

from oaknut_dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut_dfs.catalogue import FileEntry
from oaknut_dfs.catalogued_surface import CataloguedSurface
from oaknut_dfs.surface import DiscImage, SurfaceSpec


class DFS:
    """High-level DFS filesystem operations."""

    def __init__(self, catalogued_surface: CataloguedSurface):
        """
        Initialize with a catalogued surface.

        Args:
            catalogued_surface: A CataloguedSurface instance
        """
        self._catalogued_surface = catalogued_surface
        self._current_directory = "$"  # Default directory

    # Named constructors
    @classmethod
    def from_ssd(cls, buffer: memoryview) -> "DFS":
        """
        Create from SSD buffer.

        Args:
            buffer: SSD disk image buffer (single-sided)

        Returns:
            DFS instance
        """
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)
        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)
        return cls(catalogued)

    @classmethod
    def from_dsd(cls, buffer: memoryview, side: int) -> "DFS":
        """
        Create from DSD buffer (specify side 0 or 1).

        Args:
            buffer: DSD disk image buffer (double-sided)
            side: Which side to use (0 or 1)

        Returns:
            DFS instance
        """
        if side not in (0, 1):
            raise ValueError(f"Side must be 0 or 1, got {side}")

        # DSD: 2 sides, interleaved by track
        # Each side has 40 tracks, but tracks alternate (0, 2, 4,... for side 0; 1, 3, 5,... for side 1)
        spec0 = SurfaceSpec(
            num_tracks=40,  # 40 tracks per side
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=5120,  # Skip 2 tracks (one for each side)
        )
        spec1 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=2560,  # Offset by one track
            track_stride_bytes=5120,  # Skip 2 tracks
        )
        disc = DiscImage(buffer, [spec0, spec1])
        surface = disc.surface(side)
        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)
        return cls(catalogued)

    # File operations
    def load(self, filename: str) -> bytes:
        """
        Load file data (*LOAD).

        Args:
            filename: File to load (e.g., "$.HELLO" or "HELLO")

        Returns:
            File contents

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        return self._catalogued_surface.read_file(filename)

    def save(
        self,
        filename: str,
        data: bytes,
        load_address: int = 0,
        exec_address: int = 0,
        locked: bool = False,
    ) -> None:
        """
        Save file (*SAVE).

        Args:
            filename: Filename (e.g., "$.HELLO" or "HELLO")
            data: File contents
            load_address: Load address (default 0)
            exec_address: Execution address (default 0)
            locked: Whether to lock the file (default False)

        Raises:
            ValueError: If filename invalid or disk full
        """
        directory, name = self._parse_filename(filename)
        self._catalogued_surface.write_file(
            name, directory, data, load_address, exec_address, locked
        )

    def save_text(
        self, filename: str, text: str, encoding: str = "utf-8", **kwargs
    ) -> None:
        """
        Save text string to file.

        Args:
            filename: Filename
            text: Text content
            encoding: Text encoding (default utf-8)
            **kwargs: Additional arguments for save() (load_address, exec_address, locked)

        Raises:
            ValueError: If filename invalid or disk full
        """
        data = text.encode(encoding)
        self.save(filename, data, **kwargs)

    def save_from_file(self, filename: str, source_filepath: str, **kwargs) -> None:
        """
        Save file from host filesystem.

        Args:
            filename: DFS filename
            source_filepath: Path to source file on host
            **kwargs: Additional arguments for save() (load_address, exec_address, locked)

        Raises:
            FileNotFoundError: If source file doesn't exist
            ValueError: If filename invalid or disk full
        """
        from pathlib import Path

        data = Path(source_filepath).read_bytes()
        self.save(filename, data, **kwargs)

    def delete(self, filename: str) -> None:
        """
        Delete file (*DELETE).

        Args:
            filename: File to delete

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is locked
        """
        self._catalogued_surface.delete_file(filename)

    def rename(self, old_name: str, new_name: str) -> None:
        """
        Rename file (*RENAME).

        Args:
            old_name: Current filename
            new_name: New filename

        Raises:
            FileNotFoundError: If old file doesn't exist
            ValueError: If new filename invalid
        """
        self._catalogued_surface.catalogue.rename_file(old_name, new_name)

    def lock(self, filename: str) -> None:
        """
        Lock file (*ACCESS +L).

        Args:
            filename: File to lock

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        self._catalogued_surface.catalogue.lock_file(filename)

    def unlock(self, filename: str) -> None:
        """
        Unlock file (*ACCESS -L).

        Args:
            filename: File to unlock

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        self._catalogued_surface.catalogue.unlock_file(filename)

    def copy_file(self, source: str, dest: str) -> None:
        """
        Copy file within disk.

        Args:
            source: Source filename
            dest: Destination filename

        Raises:
            FileNotFoundError: If source doesn't exist
            ValueError: If destination filename invalid or disk full
        """
        entry = self._catalogued_surface.find_file(source)
        if entry is None:
            raise FileNotFoundError(f"File not found: {source}")

        # Read file data
        data = self._catalogued_surface.read_file(source)

        # Write to new location with same metadata
        directory, name = self._parse_filename(dest)
        self._catalogued_surface.write_file(
            name, directory, data, entry.load_address, entry.exec_address, entry.locked
        )

    # Disk metadata
    @property
    def title(self) -> str:
        """Get disk title."""
        return self._catalogued_surface.disk_info.title

    @title.setter
    def title(self, value: str) -> None:
        """Set disk title (max 12 chars)."""
        self._catalogued_surface.catalogue.set_title(value)

    @property
    def boot_option(self) -> int:
        """Get boot option (0-3)."""
        return self._catalogued_surface.disk_info.boot_option

    @boot_option.setter
    def boot_option(self, value: int) -> None:
        """
        Set boot option (*OPT 4,n).

        Args:
            value: Boot option (0-3)

        Raises:
            ValueError: If value not in 0-3 range
        """
        self._catalogued_surface.catalogue.set_boot_option(value)

    # File listing
    @property
    def files(self) -> list[FileEntry]:
        """List all files (*CAT)."""
        return self._catalogued_surface.list_files()

    # Directory navigation
    @property
    def current_directory(self) -> str:
        """Get current working directory."""
        return self._current_directory

    def change_directory(self, directory: str) -> None:
        """
        Change current working directory (*DIR).

        Args:
            directory: Directory letter ($ or A-Z)

        Raises:
            ValueError: If directory invalid
        """
        if not (directory == "$" or (len(directory) == 1 and directory.isalpha())):
            raise ValueError(f"Invalid directory: {directory}")
        self._current_directory = directory.upper()

    def list_directory(self, directory: str = None) -> list[FileEntry]:
        """
        List files in directory.

        Args:
            directory: Directory to list (None = current)

        Returns:
            List of files in directory
        """
        target_dir = directory.upper() if directory else self._current_directory
        return [f for f in self.files if f.directory == target_dir]

    @property
    def free_sectors(self) -> int:
        """Get number of free 256-byte sectors available."""
        return self._catalogued_surface.free_sectors

    @property
    def info(self) -> dict:
        """
        Get comprehensive disk information.

        Returns:
            Dict with: title, num_files, total_sectors, free_sectors, boot_option
        """
        disk_info = self._catalogued_surface.disk_info
        return {
            "title": disk_info.title,
            "num_files": disk_info.num_files,
            "total_sectors": disk_info.total_sectors,
            "free_sectors": self.free_sectors,
            "boot_option": disk_info.boot_option,
        }

    def exists(self, filename: str) -> bool:
        """
        Check if file exists.

        Args:
            filename: File to check

        Returns:
            True if file exists, False otherwise
        """
        return self._catalogued_surface.find_file(filename) is not None

    def get_file_info(self, filename: str):
        """
        Get detailed file information.

        Args:
            filename: File to query

        Returns:
            FileInfo with complete metadata

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        from oaknut_dfs.catalogue import FileInfo

        entry = self._catalogued_surface.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        return FileInfo(
            name=entry.path,
            directory=entry.directory,
            filename=entry.filename,
            locked=entry.locked,
            load_address=entry.load_address,
            exec_address=entry.exec_address,
            length=entry.length,
            start_sector=entry.start_sector,
            sectors=entry.sectors_required,
        )

    def validate(self) -> list[str]:
        """
        Validate disk integrity.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check catalog structure
        disk_info = self._catalogued_surface.disk_info
        if disk_info.num_files > self._catalogued_surface.catalogue.max_files:
            errors.append(
                f"Too many files: {disk_info.num_files} > "
                f"{self._catalogued_surface.catalogue.max_files}"
            )

        # Check for overlapping files
        files = self._catalogued_surface.list_files()
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
        total_sectors = self._catalogued_surface._surface.num_sectors
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

        Reads all files into memory, deletes them, then writes them back
        sequentially. This consolidates all free space at the end.

        Returns:
            Number of files compacted

        Raises:
            PermissionError: If any file is locked
        """
        files = self.files

        # Check for locked files
        locked_files = [f for f in files if f.locked]
        if locked_files:
            names = ", ".join(f.path for f in locked_files)
            raise PermissionError(f"Cannot compact: locked files present: {names}")

        if not files:
            return 0

        # Read all files into memory (with metadata)
        file_data = []
        for entry in files:
            data = self.load(entry.path)
            file_data.append(
                {
                    "name": entry.filename,
                    "directory": entry.directory,
                    "data": data,
                    "load_address": entry.load_address,
                    "exec_address": entry.exec_address,
                    "locked": entry.locked,
                }
            )

        # Delete all files
        for entry in files:
            self.delete(entry.path)

        # Write them back (will be sequential)
        for file_info in file_data:
            self.save(
                f"{file_info['directory']}.{file_info['name']}",
                file_info["data"],
                file_info["load_address"],
                file_info["exec_address"],
                file_info["locked"],
            )

        return len(file_data)

    def export_all(self, target_dirpath: str, preserve_metadata: bool = True) -> None:
        """
        Export all files to directory with optional .inf metadata files.

        Args:
            target_dirpath: Directory path to export to
            preserve_metadata: Create .inf files with DFS metadata (default True)

        Raises:
            OSError: If directory cannot be created or files cannot be written
        """
        from pathlib import Path

        target = Path(target_dirpath)
        target.mkdir(parents=True, exist_ok=True)

        for entry in self.files:
            # Export file data
            data = self.load(entry.path)
            file_path = target / f"{entry.directory}.{entry.filename}"
            file_path.write_bytes(data)

            # Export metadata
            if preserve_metadata:
                inf_path = target / f"{entry.directory}.{entry.filename}.inf"
                locked_str = " Locked" if entry.locked else ""
                inf_content = (
                    f"$.{entry.filename} "
                    f"{entry.load_address:08X} "
                    f"{entry.exec_address:08X} "
                    f"{entry.length:08X}"
                    f"{locked_str}\n"
                )
                inf_path.write_text(inf_content)

    def import_from_inf(self, data_filepath: str, inf_filepath: str = None) -> None:
        """
        Import file with metadata from .inf file.

        Args:
            data_filepath: Path to data file
            inf_filepath: Path to .inf file (defaults to data_filepath + '.inf')

        Raises:
            FileNotFoundError: If data file doesn't exist
            OSError: If files cannot be read
        """
        from pathlib import Path

        data_file = Path(data_filepath)
        inf_file = Path(inf_filepath) if inf_filepath else Path(str(data_filepath) + ".inf")

        # Read data
        data = data_file.read_bytes()

        # Parse .inf if it exists
        if inf_file.exists():
            inf_line = inf_file.read_text().strip()
            parts = inf_line.split()
            filename = parts[0]
            load_addr = int(parts[1], 16) if len(parts) > 1 else 0
            exec_addr = int(parts[2], 16) if len(parts) > 2 else 0
            locked = "Locked" in inf_line
        else:
            filename = f"$.{data_file.stem}"
            load_addr = 0
            exec_addr = 0
            locked = False

        self.save(filename, data, load_addr, exec_addr, locked)

    # Pythonic protocols
    def __contains__(self, filename: str) -> bool:
        """Support 'in' operator for file existence."""
        return self.exists(filename)

    def __iter__(self):
        """Iterate over files."""
        return iter(self.files)

    def __len__(self) -> int:
        """Number of files on disk."""
        return len(self.files)

    def __repr__(self) -> str:
        """Debug representation."""
        return (
            f"DFS(title={self.title!r}, files={len(self.files)}, "
            f"free_sectors={self.free_sectors})"
        )

    def __str__(self) -> str:
        """User-friendly representation."""
        return f"DFS Disk: {self.title} ({len(self.files)} files, {self.free_sectors} sectors free)"

    # Helpers
    def _parse_filename(self, filename: str) -> tuple[str, str]:
        """
        Parse filename into (directory, name).

        Args:
            filename: Filename to parse (e.g., "$.HELLO" or "HELLO")

        Returns:
            Tuple of (directory, name)
        """
        if "." in filename:
            directory, name = filename.split(".", 1)
            return directory, name
        # Default to $ directory
        return "$", filename

"""High-level DFS filesystem operations."""

from typing import Optional

from oaknut_dfs.catalogue import FileEntry
from oaknut_dfs.catalogued_surface import CataloguedSurface
from oaknut_dfs.formats import DiskFormat
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
    def from_buffer(
        cls, buffer: memoryview, disk_format: DiskFormat, side: int = 0
    ) -> "DFS":
        """
        Create DFS from buffer using specified disk format.

        Args:
            buffer: Disk image buffer
            disk_format: DiskFormat specifying geometry and catalogue type
            side: Which surface to use (0-based index, default 0)

        Returns:
            DFS instance for the specified side

        Raises:
            IndexError: If side index is out of range for the format
            KeyError: If catalogue_name is not registered
            ValueError: If buffer size doesn't match format requirements

        Examples:
            # Single-sided 40-track SSD
            dfs = DFS.from_buffer(buffer, ACORN_DFS_40T_SINGLE_SIDED)

            # Double-sided 40-track DSD (side 0)
            dfs = DFS.from_buffer(buffer, ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=0)

            # Double-sided 40-track DSD (side 1)
            dfs = DFS.from_buffer(buffer, ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=1)

            # 80-track sequential DSD
            dfs = DFS.from_buffer(buffer, ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL, side=1)
        """
        from oaknut_dfs.catalogue import Catalogue

        # Validate side parameter
        num_surfaces = len(disk_format.surface_specs)
        if not 0 <= side < num_surfaces:
            raise IndexError(f"side must be in range [0, {num_surfaces}), got {side}")

        # Look up catalogue class from registry
        if disk_format.catalogue_name not in Catalogue._registry:
            raise KeyError(
                f"Unknown catalogue type: {disk_format.catalogue_name!r}. "
                f"Available: {list(Catalogue._registry.keys())}"
            )
        catalogue_class = Catalogue._registry[disk_format.catalogue_name]

        # Create disc and surface
        disc = DiscImage(buffer, disk_format.surface_specs)
        surface = disc.surface(side)
        catalogued = CataloguedSurface(surface, catalogue_class)

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
        parsed = self._catalogued_surface.catalogue.parse_filename(filename)
        self._catalogued_surface.write_file(
            parsed.filename, parsed.directory, data, load_address, exec_address, locked
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

        # Parse destination using catalogue
        parsed = self._catalogued_surface.catalogue.parse_filename(dest)

        # Write to new location with same metadata
        self._catalogued_surface.write_file(
            parsed.filename, parsed.directory, data, entry.load_address, entry.exec_address, entry.locked
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
        # Delegate validation to catalogue
        self._catalogued_surface.catalogue.validate_directory(directory)
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

        Delegates to catalogue for catalogue-specific validation.

        Returns:
            List of error messages (empty if valid)
        """
        return self._catalogued_surface.catalogue.validate()

    def compact(self) -> int:
        """
        Compact disk by removing fragmentation.

        Delegates to catalogue which works at the sector level to
        rebuild entries sequentially, consolidating all free space at the end.

        Returns:
            Number of files compacted

        Raises:
            PermissionError: If any file is locked (catalogue-specific)
        """
        return self._catalogued_surface.catalogue.compact()

    def export_file(
        self, filename: str, target_filepath: str, preserve_metadata: bool = True
    ) -> None:
        """
        Export single file to host filesystem with optional .inf metadata file.

        Args:
            filename: DFS filename to export (e.g., "$.HELLO")
            target_filepath: Path to export file to
            preserve_metadata: Create .inf file with DFS metadata (default True)

        Raises:
            FileNotFoundError: If file doesn't exist on DFS disk
            OSError: If file cannot be written
        """
        from pathlib import Path

        entry = self._catalogued_surface.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Export file data
        data = self.load(entry.path)
        file_path = Path(target_filepath)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)

        # Export metadata
        if preserve_metadata:
            inf_path = Path(str(target_filepath) + ".inf")
            locked_str = " Locked" if entry.locked else ""
            inf_content = (
                f"$.{entry.filename} "
                f"{entry.load_address:08X} "
                f"{entry.exec_address:08X} "
                f"{entry.length:08X}"
                f"{locked_str}\n"
            )
            inf_path.write_text(inf_content)

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
    # _parse_filename() removed - parsing now delegated to Catalogue layer

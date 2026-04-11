"""High-level DFS filesystem operations."""

from __future__ import annotations

import mmap
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Iterator, Union

from oaknut_file import Access, AcornMeta, MetaFormat

from oaknut_dfs import basic
from oaknut_dfs.catalogue import FileEntry
from oaknut_dfs.catalogued_surface import CataloguedSurface
from oaknut_dfs.formats import DiskFormat
from oaknut_dfs.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    export_with_metadata,
    import_with_metadata,
)
from oaknut_dfs.surface import DiscImage


# Valid DFS directory characters
_DFS_DIRECTORY_CHARS = frozenset("$ABCDEFGHIJKLMNOPQRSTUVWXYZ")


@dataclass(frozen=True)
class DFSStat:
    """DFS file/directory metadata, analogous to os.stat_result."""

    length: int
    load_address: int
    exec_address: int
    locked: bool
    start_sector: int
    is_directory: bool


class DFSPath:
    """A path within a DFS filesystem, inspired by pathlib.Path.

    DFS has a flat directory structure with single-letter directory
    prefixes ($, A-Z). DFSPath models this as a virtual root containing
    directory letters, each containing files::

        (root)          path=""
        ├── $           path="$"
        │   └── HELLO   path="$.HELLO"
        └── A           path="A"
            └── GAME    path="A.GAME"

    Navigate with the ``/`` operator::

        dfs.root / "$" / "HELLO"    # → DFSPath("$.HELLO")
    """

    def __init__(self, dfs: DFS, path: str):
        self._dfs = dfs
        self._path = path

    # --- Navigation ---

    def __truediv__(self, name: str) -> DFSPath:
        """Join path components."""
        if self._path == "":
            return DFSPath(self._dfs, name)
        return DFSPath(self._dfs, f"{self._path}.{name}")

    @property
    def parent(self) -> DFSPath:
        """Parent path: ``$.HELLO`` → ``$``; ``$`` → root; root → root."""
        if "." in self._path:
            return DFSPath(self._dfs, self._path.split(".")[0])
        elif self._path:
            return DFSPath(self._dfs, "")
        return self

    @property
    def name(self) -> str:
        """Final component: ``$.HELLO`` → ``HELLO``; ``$`` → ``$``; root → ``""``."""
        if "." in self._path:
            return self._path.split(".")[-1]
        return self._path

    @property
    def parts(self) -> tuple[str, ...]:
        """Path components as a tuple."""
        if not self._path:
            return ()
        return tuple(self._path.split("."))

    @property
    def path(self) -> str:
        """Full path string."""
        return self._path

    # --- Querying ---

    def exists(self) -> bool:
        """Check whether this path exists on disc."""
        if not self._path:
            return True  # Root always exists
        if self._is_directory_path():
            return any(
                f.directory == self._path.upper()
                for f in self._dfs.files
            )
        return self._dfs._catalogued_surface.find_file(self._path) is not None

    def is_dir(self) -> bool:
        """Check whether this path is a directory."""
        if not self._path:
            return True  # Root
        return self._is_directory_path()

    def is_file(self) -> bool:
        """Check whether this path is a file (not a directory)."""
        if not self._path or self._is_directory_path():
            return False
        return self._dfs._catalogued_surface.find_file(self._path) is not None

    def stat(self) -> DFSStat:
        """Return metadata for this path.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        if not self._path or self._is_directory_path():
            return DFSStat(
                length=0,
                load_address=0,
                exec_address=0,
                locked=False,
                start_sector=0,
                is_directory=True,
            )
        entry = self._find_entry()
        return DFSStat(
            length=entry.length,
            load_address=entry.load_address,
            exec_address=entry.exec_address,
            locked=entry.locked,
            start_sector=entry.start_sector,
            is_directory=False,
        )

    # --- Directory operations ---

    def iterdir(self) -> Iterator[DFSPath]:
        """Iterate over directory contents.

        On root: yields a DFSPath for each directory letter that has files.
        On a directory: yields a DFSPath for each file in that directory.

        Raises:
            ValueError: If this path is a file, not a directory.
        """
        if not self._path:
            # Root: yield populated directory letters
            seen = set()
            for f in self._dfs.files:
                if f.directory not in seen:
                    seen.add(f.directory)
                    yield DFSPath(self._dfs, f.directory)
        elif self._is_directory_path():
            dir_letter = self._path.upper()
            for f in self._dfs.files:
                if f.directory == dir_letter:
                    yield DFSPath(self._dfs, f.path)
        else:
            raise ValueError(f"'{self._path}' is not a directory")

    def walk(self) -> Iterator[tuple[DFSPath, list[str], list[str]]]:
        """Walk directory tree, like ``os.walk()``.

        Yields ``(dirpath, dirnames, filenames)`` tuples.
        """
        if not self._path:
            # Root: directories are children, no files at root level
            populated_dirs = sorted({f.directory for f in self._dfs.files})
            yield self, populated_dirs, []
            for dir_letter in populated_dirs:
                dir_path = DFSPath(self._dfs, dir_letter)
                filenames = [
                    f.filename for f in self._dfs.files
                    if f.directory == dir_letter
                ]
                yield dir_path, [], filenames
        elif self._is_directory_path():
            dir_letter = self._path.upper()
            filenames = [
                f.filename for f in self._dfs.files
                if f.directory == dir_letter
            ]
            yield self, [], filenames

    # --- File operations ---

    def read_bytes(self) -> bytes:
        """Read file contents (*LOAD).

        Raises:
            ValueError: If this path is a directory.
            FileNotFoundError: If the file does not exist.
        """
        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot read directory as file: '{self._path}'")
        return self._dfs._catalogued_surface.read_file(self._path)

    def read_text(self, *, encoding: str = "acorn") -> str:
        """Read file contents as text using the specified encoding.

        Args:
            encoding: Text encoding (default ``"acorn"``).

        Raises:
            ValueError: If this path is a directory.
            FileNotFoundError: If the file does not exist.
        """
        return self.read_bytes().decode(encoding)

    def write_bytes(
        self,
        data: bytes,
        *,
        load_address: int = 0,
        exec_address: int = 0,
        locked: bool = False,
    ) -> None:
        """Write file contents (*SAVE).

        Raises:
            ValueError: If this path is a directory or filename is invalid.
        """
        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot write to directory: '{self._path}'")
        parsed = self._dfs._catalogued_surface.catalogue.parse_filename(self._path)
        self._dfs._catalogued_surface.write_file(
            parsed.filename, parsed.directory, data, load_address, exec_address, locked
        )

    def read_basic(self) -> str:
        """Read a BBC BASIC program and return its detokenised source.

        Composes :meth:`read_bytes` with
        :func:`oaknut_dfs.basic.detokenise`. Never compose a BASIC
        program with :meth:`read_text` — tokenised BASIC is bytecode,
        not text, and decoding it through a character codec will
        produce garbage.

        Raises:
            ValueError: If this path is a directory.
            FileNotFoundError: If the file does not exist.
            NotImplementedError: Until the detokeniser is implemented.
        """
        return basic.detokenise(self.read_bytes())

    def write_basic(
        self,
        source: str,
        *,
        load_address: int = basic.BBC_BASIC_LOAD_ADDRESS,
        exec_address: int = 0,
        locked: bool = False,
    ) -> None:
        """Write a BBC BASIC program, tokenising the source first.

        Composes :func:`oaknut_dfs.basic.tokenise` with
        :meth:`write_bytes`. Defaults the load address to the BBC
        Micro's canonical ``0x1900``; pass
        :data:`oaknut_dfs.basic.ELECTRON_BASIC_LOAD_ADDRESS` for
        Electron programs.

        Args:
            source: BBC BASIC source text.
            load_address: Load address (default ``0x1900``).
            exec_address: Execution address (default 0).
            locked: Whether to lock the file (default False).

        Raises:
            ValueError: If this path is a directory or filename is invalid.
            NotImplementedError: Until the tokeniser is implemented.
        """
        self.write_bytes(
            basic.tokenise(source),
            load_address=load_address,
            exec_address=exec_address,
            locked=locked,
        )

    def write_text(
        self,
        text: str,
        *,
        encoding: str = "acorn",
        load_address: int = 0,
        exec_address: int = 0,
        locked: bool = False,
    ) -> None:
        """Write text contents using the specified encoding.

        Args:
            text: Text to write.
            encoding: Text encoding (default ``"acorn"``).
            load_address: Load address (default 0).
            exec_address: Execution address (default 0).
            locked: Whether to lock the file (default False).
        """
        self.write_bytes(
            text.encode(encoding),
            load_address=load_address,
            exec_address=exec_address,
            locked=locked,
        )

    # --- Modification ---

    def rename(self, target: Union[str, DFSPath]) -> DFSPath:
        """Rename file, returns new DFSPath.

        Raises:
            FileNotFoundError: If this file doesn't exist.
        """
        target_path = target._path if isinstance(target, DFSPath) else target
        self._dfs._catalogued_surface.catalogue.rename_file(self._path, target_path)
        return DFSPath(self._dfs, target_path)

    def unlink(self) -> None:
        """Delete file (*DELETE).

        Raises:
            FileNotFoundError: If the file doesn't exist.
            PermissionError: If the file is locked.
        """
        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot unlink directory: '{self._path}'")
        self._dfs._catalogued_surface.delete_file(self._path)

    def lock(self) -> None:
        """Lock file (*ACCESS +L)."""
        self._dfs._catalogued_surface.catalogue.lock_file(self._path)

    def unlock(self) -> None:
        """Unlock file (*ACCESS -L)."""
        self._dfs._catalogued_surface.catalogue.unlock_file(self._path)

    # --- Host filesystem transfer ---

    def export_file(
        self,
        target_filepath: Union[str, PathLike],
        *,
        meta_format: MetaFormat | None = DEFAULT_EXPORT_META_FORMAT,
        owner: int = 0,
    ) -> Path:
        """Export file to host filesystem, emitting Acorn metadata.

        Args:
            target_filepath: Destination path on the host.
            meta_format: How to encode metadata. Defaults to traditional
                INF sidecar. Pass ``None`` to write only the data.
                Filename-encoded formats rewrite the target filename.
            owner: Econet owner ID, used only by PiEconetBridge formats.

        Returns:
            The actual path that was written. Equal to *target_filepath*
            except for filename-encoded formats.
        """
        entry = self._find_entry()
        data = self.read_bytes()
        attr = int(Access.R | Access.W)
        if entry.locked:
            attr |= int(Access.L)
        meta = AcornMeta(
            load_addr=entry.load_address,
            exec_addr=entry.exec_address,
            attr=attr,
        )
        return export_with_metadata(
            data,
            Path(target_filepath),
            meta,
            meta_format=meta_format,
            owner=owner,
            filename=entry.path,
        )

    def import_file(
        self,
        source_filepath: Union[str, PathLike],
        *,
        meta_formats: Sequence[MetaFormat] = DEFAULT_IMPORT_META_FORMATS,
    ) -> None:
        """Import a file from the host filesystem.

        The DFS filename is taken from this ``DFSPath``, not from the
        source file or any sidecar. Metadata (load/exec addresses,
        locked flag) is resolved by trying *meta_formats* in order;
        the first reader to match wins. DFS only stores the locked
        attribute bit, so public/execute attributes from the source
        metadata are silently discarded.

        Args:
            source_filepath: Path to the source file on the host.
            meta_formats: Ordered cascade of metadata schemes to try.
                Defaults to ``DEFAULT_IMPORT_META_FORMATS``.
        """
        source = Path(source_filepath)
        data = source.read_bytes()
        _, _, meta = import_with_metadata(source, meta_formats=meta_formats)

        load_address = meta.load_addr or 0
        exec_address = meta.exec_addr or 0
        locked = bool((meta.attr or 0) & int(Access.L))

        self.write_bytes(
            data,
            load_address=load_address,
            exec_address=exec_address,
            locked=locked,
        )

    # --- Protocols ---

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"DFSPath({self._path!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DFSPath):
            return NotImplemented
        return self._dfs is other._dfs and self._path.upper() == other._path.upper()

    def __hash__(self) -> int:
        return hash(self._path.upper())

    def __iter__(self) -> Iterator[DFSPath]:
        """Shorthand for ``iterdir()``."""
        return self.iterdir()

    def __contains__(self, name: str) -> bool:
        """Check if *name* exists in this directory."""
        if not self._path:
            # Root: check if directory letter has files
            return any(f.directory == name.upper() for f in self._dfs.files)
        elif self._is_directory_path():
            dir_letter = self._path.upper()
            return any(
                f.directory == dir_letter and f.filename.upper() == name.upper()
                for f in self._dfs.files
            )
        return False

    # --- Internal helpers ---

    def _is_directory_path(self) -> bool:
        """Check if this path represents a directory (single letter)."""
        return len(self._path) == 1 and self._path.upper() in _DFS_DIRECTORY_CHARS

    def _find_entry(self) -> FileEntry:
        """Find the FileEntry for this path.

        Raises:
            FileNotFoundError: If file not found.
        """
        entry = self._dfs._catalogued_surface.find_file(self._path)
        if entry is None:
            raise FileNotFoundError(f"File not found: {self._path}")
        return entry


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
    @staticmethod
    @contextmanager
    def from_file(
        filepath: Union[str, PathLike],
        disk_format: DiskFormat,
        side: int = 0,
        mode: str = "rb",
    ) -> Iterator["DFS"]:
        """
        Open a disc image file as a context manager.

        When opened in read-write mode ("r+b"), changes are written
        through to the file via mmap.

        Args:
            filepath: Path to the disc image file (.ssd or .dsd)
            disk_format: DiskFormat specifying geometry and catalogue type
            side: Which surface to use (0-based index, default 0)
            mode: File open mode — "rb" for read-only (default),
                  "r+b" for read-write

        Yields:
            DFS instance backed by the file

        Raises:
            FileNotFoundError: If the file does not exist
            IndexError: If side index is out of range for the format
            ValueError: If mode is not "rb" or "r+b"

        Examples:
            # Read-only access
            with DFS.from_file("Zalaga.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:
                print(dfs.title)
                data = (dfs.root / "$" / "ZALAGA").read_bytes()

            # Read-write access
            with DFS.from_file("disc.ssd", ACORN_DFS_40T_SINGLE_SIDED, mode="r+b") as dfs:
                (dfs.root / "$" / "HELLO").write_bytes(b"Hello!")
        """
        if mode not in ("rb", "r+b"):
            raise ValueError(f"mode must be 'rb' or 'r+b', got {mode!r}")

        access = mmap.ACCESS_READ if mode == "rb" else mmap.ACCESS_WRITE
        with open(filepath, mode) as f:
            mm = mmap.mmap(f.fileno(), 0, access=access)
            dfs = DFS.from_buffer(memoryview(mm), disk_format, side)
            try:
                yield dfs
            finally:
                if mode == "r+b":
                    mm.flush()

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

    @classmethod
    def create(
        cls,
        disk_format: DiskFormat,
        *,
        side: int = 0,
        title: str = "",
        boot_option: int = 0,
    ) -> DFS:
        """Create a new in-memory DFS disc image with an empty catalogue.

        Args:
            disk_format: DiskFormat specifying geometry and catalogue type.
            side: Which surface to initialise (0-based, default 0).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Returns:
            DFS instance backed by an in-memory buffer.
        """
        from oaknut_dfs.catalogue import Catalogue

        # Calculate buffer size from the format's surface specs
        specs = disk_format.surface_specs
        buffer_size = 0
        for spec in specs:
            end = (
                spec.track_zero_offset_bytes
                + (spec.num_tracks - 1) * spec.track_stride_bytes
                + spec.sectors_per_track * spec.bytes_per_sector
            )
            buffer_size = max(buffer_size, end)

        buffer = memoryview(bytearray(buffer_size))
        disc = DiscImage(buffer, specs)
        surface = disc.surface(side)
        total_sectors = surface.num_sectors

        # Look up and initialise the catalogue
        catalogue_class = Catalogue._registry[disk_format.catalogue_name]
        catalogue_class.initialise(surface, total_sectors, title, boot_option)

        catalogued = CataloguedSurface(surface, catalogue_class)
        return cls(catalogued)

    @staticmethod
    @contextmanager
    def create_file(
        filepath: Union[str, PathLike],
        disk_format: DiskFormat,
        *,
        side: int = 0,
        title: str = "",
        boot_option: int = 0,
    ) -> Iterator[DFS]:
        """Create a new DFS disc image file with an empty catalogue.

        The file is created at *filepath* with the correct size and
        opened read-write via mmap. Changes are flushed on exit.

        Args:
            filepath: Path for the new disc image file.
            disk_format: DiskFormat specifying geometry and catalogue type.
            side: Which surface to initialise (0-based, default 0).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Yields:
            DFS instance backed by the file.
        """
        from oaknut_dfs.catalogue import Catalogue

        # Calculate file size
        specs = disk_format.surface_specs
        file_size = 0
        for spec in specs:
            end = (
                spec.track_zero_offset_bytes
                + (spec.num_tracks - 1) * spec.track_stride_bytes
                + spec.sectors_per_track * spec.bytes_per_sector
            )
            file_size = max(file_size, end)

        # Write a blank file of the correct size
        with open(filepath, "wb") as f:
            f.write(b"\x00" * file_size)

        # Reopen read-write with mmap
        with open(filepath, "r+b") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)
            buffer = memoryview(mm)
            disc = DiscImage(buffer, specs)
            surface = disc.surface(side)
            total_sectors = surface.num_sectors

            catalogue_class = Catalogue._registry[disk_format.catalogue_name]
            catalogue_class.initialise(surface, total_sectors, title, boot_option)

            catalogued = CataloguedSurface(surface, catalogue_class)
            dfs = DFS(catalogued)
            try:
                yield dfs
            finally:
                mm.flush()

    # Path API
    @property
    def root(self) -> DFSPath:
        """The virtual root directory containing all directory letters."""
        return DFSPath(self, "")

    def path(self, path: str) -> DFSPath:
        """Create a DFSPath from a path string.

        Args:
            path: DFS path string, e.g. ``"$"``, ``"$.HELLO"``, or ``""`` for root.
        """
        return DFSPath(self, path)

    # Disc metadata
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

    def export_all(
        self,
        target_dirpath: Union[str, PathLike],
        *,
        meta_format: MetaFormat | None = DEFAULT_EXPORT_META_FORMAT,
        owner: int = 0,
    ) -> None:
        """Export all files in the catalogue to a host directory.

        Args:
            target_dirpath: Directory to export into. Created if missing.
            meta_format: Metadata encoding. Defaults to traditional INF.
                ``None`` suppresses metadata (data files only). See
                :func:`oaknut_dfs.host_bridge.export_with_metadata`.
            owner: Econet owner ID, used only by PiEconetBridge formats.

        Raises:
            OSError: If directory cannot be created or files cannot be written.
        """
        target = Path(target_dirpath)
        target.mkdir(parents=True, exist_ok=True)

        for entry in self.files:
            target_filepath = target / f"{entry.directory}.{entry.filename}"
            path = DFSPath(self, entry.path)
            path.export_file(
                target_filepath,
                meta_format=meta_format,
                owner=owner,
            )

    # Pythonic protocols
    def __contains__(self, filename: str) -> bool:
        """Support 'in' operator for file existence."""
        return self._catalogued_surface.find_file(filename) is not None

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

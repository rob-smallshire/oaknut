"""High-level DFS filesystem operations."""

from __future__ import annotations

import mmap
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Union

import oaknut.basic as basic
from oaknut.dfs.catalogue import FileEntry
from oaknut.dfs.catalogued_surface import CataloguedSurface
from oaknut.dfs.formats import BYTES_PER_SECTOR, DiscFormat
from oaknut.discimage.surface import DiscImage
from oaknut.file import Access, AcornMeta, AcornPath, MetaFormat, resolving_io
from oaknut.file.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    export_with_metadata,
    import_with_metadata,
)

if TYPE_CHECKING:
    from oaknut.dfs.exceptions import DFSValidationError
    from oaknut.file import BootOption

# Valid DFS directory characters
_DFS_DIRECTORY_CHARS = frozenset("$ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def detect_dfs_format(filepath: Union[str, PathLike]) -> DiscFormat:
    """Auto-detect a DFS :class:`DiscFormat` from the file extension and size.

    Recognised pairs:

    ============  =================  ================================
    Extension     Size               Format
    ============  =================  ================================
    ``.ssd``      100 KiB (102 400)  ``ACORN_DFS_40T_SINGLE_SIDED``
    ``.ssd``      200 KiB (204 800)  ``ACORN_DFS_80T_SINGLE_SIDED``
    ``.dsd``      200 KiB (204 800)  ``ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED``
    ``.dsd``      400 KiB (409 600)  ``ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED``
    ============  =================  ================================

    The sequential-double-sided variants share their byte count with
    the interleaved forms, so detection cannot distinguish them — pass
    ``disc_format=`` explicitly for those.

    Raises:
        FileNotFoundError: If *filepath* does not exist.
        ValueError: If extension or size is not in the table above.
    """
    from oaknut.dfs.formats import (
        ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
        ACORN_DFS_40T_SINGLE_SIDED,
        ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
        ACORN_DFS_80T_SINGLE_SIDED,
    )

    filepath = Path(filepath)
    ext = filepath.suffix.lower()
    size = filepath.stat().st_size

    if ext == ".ssd":
        if size <= 102_400:
            return ACORN_DFS_40T_SINGLE_SIDED
        if size <= 204_800:
            return ACORN_DFS_80T_SINGLE_SIDED
    elif ext == ".dsd":
        if size <= 204_800:
            return ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED
        if size <= 409_600:
            return ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

    raise ValueError(
        f"could not auto-detect DFS format for {filepath.name!r} "
        f"(extension {ext!r}, size {size} bytes); pass disc_format= explicitly"
    )


def _coerce_access_to_locked(access: "Access | None") -> bool:
    """Project the canonical ``access`` value down to DFS's lone L bit.

    DFS only stores the locked bit; the richer :class:`Access` flags
    collapse to ``Access.L`` presence. ``None`` (the default) maps to
    unlocked; an :class:`Access` value is masked against ``Access.L``.
    """
    if access is None:
        return False
    return bool(int(access) & int(Access.L))


@dataclass(frozen=True)
class DFSStat:
    """DFS file/directory metadata, analogous to os.stat_result.

    Conforms to :class:`oaknut.file.Stat` — :attr:`access` is
    synthesised from :attr:`locked` plus DFS's implicit always-WR
    base, and :attr:`date` is always ``None`` because DFS does not
    store per-file date stamps.
    """

    length: int
    load_address: int
    exec_address: int
    locked: bool
    start_sector: int
    is_directory: bool

    @property
    def access(self) -> "Access":
        """Canonical :class:`~oaknut.file.Access` flags.

        DFS only stores a single ``locked`` bit, so the result is
        always owner-read + owner-write, plus ``L`` if locked.
        """
        from oaknut.file import Access

        flags = Access.R | Access.W
        if self.locked:
            flags |= Access.L
        return flags

    @property
    def date(self) -> None:
        """DFS does not record per-file dates — always ``None``."""
        return None


class DFSPath(AcornPath):
    """A path within a DFS filesystem, inspired by pathlib.Path.

    **DFS is not a hierarchical filesystem.** Its on-disc catalogue is a
    *flat* list of up to 31 entries, each tagged with a single-character
    "directory" — one of ``$``, ``A``–``Z``. The directory character is a
    namespace, not a container: ``$.MYPROG`` and ``A.MYPROG`` are two
    independent files, and neither is "inside" the other. The Acorn DFS
    User Guide spells this out — quoting roughly, *"Files of the same
    name can be created on the same disc with different directories"*
    and *"the current directory and drive number is always set to drive
    0 and directory ``$`` ... they will be assumed"*.

    ``$`` is therefore the **default directory** DFS assumes when a path
    omits one; it is not a parent of ``A``–``Z``. Compare ADFS / AFS,
    which *do* have a tree rooted at ``$``.

    DFSPath models the catalogue as a notional root holding the set of
    populated directory tags, each tag in turn enumerating the files
    that carry it::

        (catalogue)     path=""
        ├── $           path="$"      (default directory)
        │   └── HELLO   path="$.HELLO"
        └── A           path="A"      (sibling of $, not inside it)
            └── GAME    path="A.GAME"

    ``dfs.root`` is the empty-string catalogue handle, not ``$`` —
    walking ``/`` from it produces paths in *any* directory letter, not
    just the default one. Navigate with the ``/`` operator and the
    ``DIR.NAME`` form::

        dfs.root / "$.HELLO"        # default directory
        dfs.root / "A.GAME"         # sibling directory A
        dfs.root / "$" / "HELLO"    # also $.HELLO (two-step form)
    """

    def __init__(self, dfs: DFS, path: str):
        self._dfs = dfs
        self._path = path

    # --- Navigation ---

    def _join_name(self, name: str) -> DFSPath:
        if self._path == "":
            return DFSPath(self._dfs, name)
        return DFSPath(self._dfs, f"{self._path}.{name}")

    def _root(self) -> DFSPath:
        return DFSPath(self._dfs, "")

    def _root_parts(self) -> tuple[str, ...]:
        return ()

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

    @resolving_io
    def exists(self) -> bool:
        """Check whether this path exists on disc."""
        if not self._path:
            return True  # Root always exists
        if self._is_directory_path():
            return any(f.directory == self._path.upper() for f in self._dfs.files)
        return self._dfs._catalogued_surface.find_file(self._path) is not None

    @resolving_io
    def is_dir(self) -> bool:
        """Check whether this path is a directory."""
        if not self._path:
            return True  # Root
        return self._is_directory_path()

    @resolving_io
    def is_file(self) -> bool:
        """Check whether this path is a file (not a directory)."""
        if not self._path or self._is_directory_path():
            return False
        return self._dfs._catalogued_surface.find_file(self._path) is not None

    @resolving_io
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

    @resolving_io
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

    # --- File operations ---

    @resolving_io
    def read_bytes(self) -> bytes:
        """Read file contents (*LOAD).

        Raises:
            ValueError: If this path is a directory.
            FileNotFoundError: If the file does not exist.
        """
        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot read directory as file: '{self._path}'")
        return self._dfs._catalogued_surface.read_file(self._path)

    @resolving_io
    def write_bytes(
        self,
        data: bytes,
        *,
        load_address: int = 0,
        exec_address: int = 0,
        access: "Access | None" = None,
        date: object = None,
    ) -> None:
        """Write file contents (*SAVE).

        ``access`` accepts the canonical :class:`oaknut.file.Access`
        flags, a plain ``bool`` (``True`` => locked, ``False`` =>
        unlocked), or ``None`` to use the filesystem default
        (unlocked). DFS only stores the locked bit, so any other
        :class:`Access` bits are silently dropped.

        ``date`` is accepted for cross-filesystem signature uniformity
        but silently ignored — DFS does not store per-file dates.

        Raises:
            ValueError: If this path is a directory or filename is invalid.
        """
        del date  # accepted for signature uniformity only

        locked_val = _coerce_access_to_locked(access)

        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot write to directory: '{self._path}'")
        parsed = self._dfs._catalogued_surface.catalogue.parse_filename(self._path)
        self._dfs._catalogued_surface.write_file(
            parsed.filename, parsed.directory, data, load_address, exec_address, locked_val
        )

    @resolving_io
    def read_basic(self) -> str:
        """Read a BBC BASIC program and return its detokenised source.

        Composes :meth:`read_bytes` with
        :func:`oaknut.dfs.basic.detokenise`. Never compose a BASIC
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
        access: "Access | None" = None,
    ) -> None:
        """Write a BBC BASIC program, tokenising the source first.

        Composes :func:`oaknut.dfs.basic.tokenise` with
        :meth:`write_bytes`. Defaults the load address to the BBC
        Micro's canonical ``0x1900``; pass
        :data:`oaknut.dfs.basic.ELECTRON_BASIC_LOAD_ADDRESS` for
        Electron programs.

        Args:
            source: BBC BASIC source text.
            load_address: Load address (default ``0x1900``).
            exec_address: Execution address (default 0).
            access: Access flags (see :meth:`write_bytes`).

        Raises:
            ValueError: If this path is a directory or filename is invalid.
            NotImplementedError: Until the tokeniser is implemented.
        """
        self.write_bytes(
            basic.tokenise(source),
            load_address=load_address,
            exec_address=exec_address,
            access=access,
        )

    @resolving_io
    def touch(
        self,
        *,
        access: "Access | None" = None,
        exist_ok: bool = True,
    ) -> None:
        """Create an empty file at this path, mirroring :meth:`pathlib.Path.touch`.

        DFS catalogue entries carry no modification time, so touching
        an existing file is a no-op when ``exist_ok`` is ``True``.

        Args:
            access: Access flags for the new file. Ignored on existing
                files (the access is not rewritten).
            exist_ok: Default ``True`` matches pathlib. When ``False``,
                an existing file or directory at the path raises.

        Raises:
            ValueError: If this path is a DFS directory letter.
            FileExistsError: If something already exists at the path
                and ``exist_ok`` is ``False``.
        """
        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot touch a directory: '{self._path}'")
        if self.exists():
            if exist_ok:
                return
            from oaknut.dfs.exceptions import FileExistsError as DFSFileExistsError

            raise DFSFileExistsError(f"'{self._path}' already exists")
        self.write_bytes(b"", access=access)

    # --- Modification ---

    @resolving_io
    def rename(self, target: Union[str, DFSPath]) -> DFSPath:
        """Rename file, returns new DFSPath.

        Raises:
            FileNotFoundError: If this file doesn't exist.
        """
        target_path = target._path if isinstance(target, DFSPath) else target
        self._dfs._catalogued_surface.catalogue.rename_file(self._path, target_path)
        return DFSPath(self._dfs, target_path)

    @resolving_io
    def unlink(self) -> None:
        """Delete file (*DELETE).

        Raises:
            FileNotFoundError: If the file doesn't exist.
            PermissionError: If the file is locked.
        """
        if not self._path or self._is_directory_path():
            raise ValueError(f"Cannot unlink directory: '{self._path}'")
        self._dfs._catalogued_surface.delete_file(self._path)

    @resolving_io
    def lock(self) -> None:
        """Lock file (*ACCESS +L)."""
        self._dfs._catalogued_surface.catalogue.lock_file(self._path)

    @resolving_io
    def unlock(self) -> None:
        """Unlock file (*ACCESS -L)."""
        self._dfs._catalogued_surface.catalogue.unlock_file(self._path)

    @resolving_io
    def set_load_address(self, address: int) -> None:
        """Set the load address without rewriting the file data."""
        self._dfs._catalogued_surface.catalogue.set_load_address(self._path, address)

    @resolving_io
    def set_exec_address(self, address: int) -> None:
        """Set the exec address without rewriting the file data."""
        self._dfs._catalogued_surface.catalogue.set_exec_address(self._path, address)

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
            load_address=entry.load_address,
            exec_address=entry.exec_address,
            access=attr,
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

        self.write_bytes(
            data,
            load_address=meta.load_address or 0,
            exec_address=meta.exec_address or 0,
            access=meta.access,
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

    @resolving_io
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
    """High-level DFS filesystem operations.

    DFS is the Acorn Disc Filing System used on BBC Micro and Electron
    floppies. The on-disc structure is a *flat* 31-entry catalogue, not
    a hierarchical tree: every entry carries a single-character
    "directory" tag (``$``, ``A``–``Z``) that namespaces files of the
    same name. See :class:`DFSPath` for the model and what this means
    for path construction.
    """

    def __init__(self, catalogued_surface: CataloguedSurface):
        """
        Initialize with a catalogued surface.

        Args:
            catalogued_surface: A CataloguedSurface instance
        """
        # _closed must be set before any attribute that property-gates
        # would touch via _require_open.
        self._closed = False
        self._cs = catalogued_surface
        self._current_directory = "$"  # Default directory

    @property
    def closed(self) -> bool:
        """Whether this handle has been closed.

        Once closed, any I/O operation raises
        :class:`oaknut.file.FilesystemClosedError`. Pure path
        manipulation on path objects bound to this handle continues
        to work.
        """
        return self._closed

    def close(self) -> None:
        """Mark this handle as closed; idempotent.

        Normally invoked automatically when the
        :meth:`from_file` / :meth:`create_file` ``with`` block exits.
        Callers that build a :class:`DFS` from a buffer directly can
        call ``close()`` to mark the lifecycle ended.
        """
        if self._closed:
            return
        self._closed = True

    def _require_open(self) -> None:
        """Raise :class:`FilesystemClosedError` if this handle is closed."""
        if self._closed:
            from oaknut.file.exceptions import FilesystemClosedError

            raise FilesystemClosedError(
                "DFS handle is closed; I/O outside the with block is not supported"
            )

    @property
    def _catalogued_surface(self) -> CataloguedSurface:
        """Access the catalogued surface, raising if the handle is closed.

        Every I/O path bottoms out in this attribute, so gating it
        here gives the runtime check we need without per-method
        ``_require_open()`` calls scattered through DFSPath.
        """
        self._require_open()
        return self._cs

    # Named constructors
    @staticmethod
    @contextmanager
    def from_file(
        filepath: Union[str, PathLike],
        disc_format: DiscFormat | None = None,
        *,
        side: int = 0,
    ) -> Iterator["DFS"]:
        """Open a disc image file as a context manager.

        The image is opened writable when host filesystem permissions
        allow, read-only otherwise. Mutations against a read-only-backed
        image raise from the mmap layer at the point of write.

        ``disc_format`` is optional — when omitted, the format is
        auto-detected from the file extension and size (see
        :func:`detect_dfs_format`).  Pass it explicitly to override
        detection (necessary for the rare sequential-double-sided
        flavour, which shares its byte count with the interleaved
        form).

        A truncated image is padded in memory with zeros; the on-disc
        file is never grown by this call. Mutations to a truncated
        image therefore land in the in-memory pad and are not
        persisted — opening a file never modifies it.

        Args:
            filepath: Path to the disc image file (``.ssd`` or ``.dsd``).
            disc_format: DiscFormat specifying geometry and catalogue
                type; auto-detected when ``None``.
            side: Which surface to use (0-based index, default 0).

        Yields:
            DFS instance backed by the file

        Raises:
            FileNotFoundError: If the file does not exist
            IndexError: If side index is out of range for the format
            ValueError: If auto-detection cannot identify the format

        Examples:
            with DFS.from_file("Zalaga.ssd") as dfs:
                print(dfs.title)
                data = (dfs.root / "$" / "ZALAGA").read_bytes()

            with DFS.from_file("disc.ssd", ACORN_DFS_40T_SINGLE_SIDED) as dfs:
                (dfs.root / "$" / "HELLO").write_bytes(b"Hello!")
        """
        from oaknut.discimage.open_image import open_image_mmap

        filepath = Path(filepath)
        if disc_format is None:
            disc_format = detect_dfs_format(filepath)
        file_size = filepath.stat().st_size
        expected_size = disc_format.image_size

        if file_size < expected_size:
            data = bytearray(filepath.read_bytes())
            dfs = DFS.from_buffer(memoryview(data), disc_format, side)
            try:
                yield dfs
            finally:
                dfs.close()
            return

        with open_image_mmap(filepath) as (mm, _writable):
            dfs = DFS.from_buffer(memoryview(mm), disc_format, side)
            try:
                yield dfs
            finally:
                dfs.close()

    @classmethod
    def from_buffer(cls, buffer: memoryview, disc_format: DiscFormat, side: int = 0) -> "DFS":
        """
        Create DFS from buffer using specified disk format.

        Args:
            buffer: Disk image buffer
            disc_format: DiscFormat specifying geometry and catalogue type
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
        from oaknut.dfs.catalogue import Catalogue

        # Validate side parameter
        num_surfaces = len(disc_format.surface_specs)
        if not 0 <= side < num_surfaces:
            raise IndexError(f"side must be in range [0, {num_surfaces}), got {side}")

        # Look up catalogue class from registry
        if disc_format.catalogue_name not in Catalogue._registry:
            raise KeyError(
                f"Unknown catalogue type: {disc_format.catalogue_name!r}. "
                f"Available: {list(Catalogue._registry.keys())}"
            )
        catalogue_class = Catalogue._registry[disc_format.catalogue_name]

        # Pad truncated images to the canonical format size
        buffer = cls._pad_buffer(buffer, disc_format)

        # Create disc and surface
        disc = DiscImage(buffer, disc_format.surface_specs)
        surface = disc.surface(side)
        catalogued = CataloguedSurface(surface, catalogue_class)

        return cls(catalogued)

    @staticmethod
    def _pad_buffer(buffer: memoryview, disc_format: DiscFormat) -> memoryview:
        """Pad a truncated buffer to the canonical format size with zero bytes.

        Accepts buffers that are shorter than the format requires, provided
        the size is a whole number of sectors (a multiple of 256 bytes).
        Full-size buffers are returned unchanged.

        Raises:
            ValueError: If the buffer size is not a multiple of the sector
                size, or if the buffer is empty.
        """
        buffer_size = len(buffer)
        expected_size = disc_format.image_size

        if buffer_size == expected_size:
            return buffer

        if buffer_size == 0:
            raise ValueError("Buffer is empty")

        if buffer_size % BYTES_PER_SECTOR != 0:
            raise ValueError(
                f"Buffer size {buffer_size} is not a multiple of "
                f"the sector size ({BYTES_PER_SECTOR} bytes)"
            )

        if buffer_size > expected_size:
            return buffer

        padded = bytearray(expected_size)
        padded[:buffer_size] = buffer
        return memoryview(padded)

    @classmethod
    def create(
        cls,
        disc_format: DiscFormat,
        *,
        side: int = 0,
        title: str = "",
        boot_option: int = 0,
    ) -> DFS:
        """Create a new in-memory DFS disc image with an empty catalogue.

        Args:
            disc_format: DiscFormat specifying geometry and catalogue type.
            side: Which surface to initialise (0-based, default 0).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Returns:
            DFS instance backed by an in-memory buffer.
        """
        from oaknut.dfs.catalogue import Catalogue

        # Calculate buffer size from the format's surface specs
        specs = disc_format.surface_specs
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
        catalogue_class = Catalogue._registry[disc_format.catalogue_name]
        catalogue_class.initialise(surface, total_sectors, title, boot_option)

        catalogued = CataloguedSurface(surface, catalogue_class)
        return cls(catalogued)

    @staticmethod
    @contextmanager
    def create_file(
        filepath: Union[str, PathLike],
        disc_format: DiscFormat | None = None,
        *,
        side: int = 0,
        title: str = "",
        boot_option: int = 0,
    ) -> Iterator[DFS]:
        """Create a new DFS disc image file with an empty catalogue.

        The file is created at *filepath* with the correct size and
        opened read-write via mmap. Changes are flushed on exit.

        ``disc_format`` is optional — when omitted it is picked from
        the filename extension (``.ssd`` ⇒ 80-track single-sided,
        ``.dsd`` ⇒ 80-track double-sided interleaved).  Pass it
        explicitly for the 40-track or sequential-double-sided
        variants.

        Args:
            filepath: Path for the new disc image file.
            disc_format: DiscFormat specifying geometry and catalogue
                type; chosen from the extension when ``None``.
            side: Which surface to initialise (0-based, default 0).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Yields:
            DFS instance backed by the file.
        """
        from oaknut.dfs.catalogue import Catalogue
        from oaknut.dfs.formats import (
            ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
            ACORN_DFS_80T_SINGLE_SIDED,
        )

        if disc_format is None:
            from oaknut.dfs.exceptions import DFSFormatError

            ext = Path(filepath).suffix.lower()
            if ext == ".ssd":
                disc_format = ACORN_DFS_80T_SINGLE_SIDED
            elif ext == ".dsd":
                disc_format = ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED
            else:
                raise DFSFormatError(
                    f"cannot pick a default DFS format for extension {ext!r}; "
                    "pass disc_format= explicitly"
                )

        # Calculate file size
        specs = disc_format.surface_specs
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

            catalogue_class = Catalogue._registry[disc_format.catalogue_name]
            catalogue_class.initialise(surface, total_sectors, title, boot_option)

            catalogued = CataloguedSurface(surface, catalogue_class)
            dfs = DFS(catalogued)
            try:
                yield dfs
            finally:
                dfs.close()
                mm.flush()

    # Path API
    @property
    def root(self) -> DFSPath:
        """A path handle representing the whole catalogue.

        DFS is a flat-catalogue filesystem (see :class:`DFSPath`); this
        handle is the empty-string entry point from which the ``/``
        operator can build a path in *any* directory letter, including
        the default ``$`` and the sibling tags ``A``–``Z``. It is
        deliberately **not** ``$`` — making it ``$`` would suggest the
        other directories live inside it, which they do not.

        For the hierarchical-root equivalent on ADFS / AFS, see
        :attr:`oaknut.adfs.ADFS.root` and :attr:`oaknut.afs.AFS.root`.
        """
        return DFSPath(self, "")

    def path(self, path: str) -> DFSPath:
        """Create a DFSPath from a path string.

        Routes through :meth:`DFSPath.__truediv__` so the
        Acorn-shell ``^`` parent token (and consecutive ``^^``)
        are interpreted the same way as in a slash-joined chain.

        Args:
            path: DFS path string, e.g. ``"$"``, ``"$.HELLO"``,
                ``"^.A.GAME"``, or ``""`` for root.
        """
        return self.root / path

    # Disc metadata
    @property
    def title(self) -> str:
        """Get disk title."""
        return self._catalogued_surface.disc_info.title

    @title.setter
    def title(self, value: str) -> None:
        """Set disk title (max 12 chars)."""
        self._catalogued_surface.catalogue.set_title(value)

    @property
    def boot_option(self) -> "BootOption":
        """Get boot option as a :class:`oaknut.file.BootOption` enum."""
        from oaknut.file import BootOption

        return BootOption(self._catalogued_surface.disc_info.boot_option)

    @boot_option.setter
    def boot_option(self, value: "BootOption | int") -> None:
        """Set boot option (``*OPT 4,n``).

        Accepts either a :class:`oaknut.file.BootOption` or a plain
        ``int`` in the range 0–3. Invalid values raise from the
        :class:`BootOption` constructor itself.
        """
        from oaknut.file import BootOption

        self._catalogued_surface.catalogue.set_boot_option(int(BootOption(value)))

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
        disc_info = self._catalogued_surface.disc_info
        return {
            "title": disc_info.title,
            "num_files": disc_info.num_files,
            "total_sectors": disc_info.total_sectors,
            "free_sectors": self.free_sectors,
            "boot_option": disc_info.boot_option,
        }

    def validate(self) -> list["DFSValidationError"]:
        """Validate disc-image integrity.

        Delegates to the underlying catalogue, which checks file
        extents, overlaps, duplicate names, and so on. Returns a list
        of :class:`oaknut.dfs.exceptions.DFSValidationError` — empty
        when the image is clean.
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
                :func:`oaknut.file.host_bridge.export_with_metadata`.
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
            f"DFS(title={self.title!r}, files={len(self.files)}, free_sectors={self.free_sectors})"
        )

    def __str__(self) -> str:
        """User-friendly representation."""
        return f"DFS Disk: {self.title} ({len(self.files)} files, {self.free_sectors} sectors free)"

    # Helpers
    # _parse_filename() removed - parsing now delegated to Catalogue layer


def expand(filepath: Union[str, PathLike], disc_format: DiscFormat) -> int:
    """Physically extend a truncated disc image file to its canonical format size.

    Appends zero bytes to *filepath* until it reaches the size required
    by *disc_format*.  The original data is preserved.

    Args:
        filepath: Path to the disc image file.
        disc_format: Target format whose ``image_size`` the file should
            match after expansion.

    Returns:
        The number of bytes appended (0 if the file was already the
        correct size).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty, not a whole number of sectors,
            or already larger than the canonical format size.
    """
    filepath = Path(filepath)
    file_size = filepath.stat().st_size
    expected_size = disc_format.image_size

    if file_size == 0:
        raise ValueError(f"{filepath.name} is empty")

    if file_size % BYTES_PER_SECTOR != 0:
        raise ValueError(
            f"{filepath.name} size ({file_size}) is not a multiple of "
            f"the sector size ({BYTES_PER_SECTOR} bytes)"
        )

    if file_size > expected_size:
        raise ValueError(
            f"{filepath.name} ({file_size} bytes) is larger than "
            f"the canonical format size ({expected_size} bytes)"
        )

    if file_size == expected_size:
        return 0

    padding = expected_size - file_size
    with open(filepath, "ab") as f:
        f.write(b"\x00" * padding)
    return padding

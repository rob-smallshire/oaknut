"""ROMFS as an oaknut.filesystem extension.

Adapts the native :class:`~oaknut.romfs.romfs.ROMFS` class to the
:class:`~oaknut.filesystem.Filesystem` contract: identification via the
paged-ROM header and a CRC-validated block chain, a
:class:`~oaknut.filesystem.Mount` over the file list, and a trivial linear
geometry (a ROM is a flat byte range, not a sectored disc).

ROMFS is flat, so the mount does not advertise
:class:`~oaknut.filesystem.HierarchicalDirectories`; it provides the
``AcornMetadata`` (load/exec + the `*RUN`-only copy-protection bit, surfaced
as ``Access.X``) and ``Titled`` capabilities. Writes are supported on
*plain* ROMFS images; a *composite* ROM (one carrying a service handler or
language after the filing system) is read-only, so its trailing code is
never corrupted.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.discimage import BYTES_PER_SECTOR, SurfaceSpec
from oaknut.file import Access, AcornMeta
from oaknut.filesystem import (
    Confidence,
    Entry,
    Filesystem,
    Geometry,
    GeometryGrammar,
    Identification,
    ImageReader,
)
from oaknut.filesystem.exceptions import ReadOnlyFilesystemError
from oaknut.romfs.block import MAX_NAME_LENGTH
from oaknut.romfs.exceptions import CRCError, NotAROMFSError, ROMFSError, TruncatedROMError
from oaknut.romfs.romfs import MAX_TITLE_LENGTH, ROMFS, ROMFSFile, build_rom_image

#: ROMFS images conventionally use this extension.
_EXTENSIONS = frozenset({".rom"})


def _linear_geometry(size: int) -> Geometry:
    """A single linear surface spanning a *size*-byte ROM.

    ROMFS has no real disc geometry; this models the ROM as one flat run of
    256-byte sectors so the framework has a geometry to carry.
    """
    sectors = max(1, size // BYTES_PER_SECTOR)
    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=sectors,
        bytes_per_sector=BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=size,
    )
    kib = size // 1024
    return Geometry((spec,), label=f"{kib} KiB ROM" if kib else f"{size}-byte ROM")


_GEOMETRY_PRESETS = {
    "8k": _linear_geometry(8 * 1024),
    "16k": _linear_geometry(16 * 1024),
}


class _ROMFSMount:
    """A :class:`~oaknut.filesystem.Mount` over a :class:`ROMFS` instance.

    Implements the flat core plus ``AcornMetadata`` and ``Titled``. The
    ``*…*`` title block is surfaced through :attr:`title`, not listed as a
    file. Mutating operations rebuild the whole ROM and write it back
    through the reader; they refuse a composite or read-only image.
    """

    def __init__(self, romfs: ROMFS, reader: ImageReader):
        self._romfs = romfs
        self._reader = reader

    # -- helpers --
    def _data_files(self) -> tuple[ROMFSFile, ...]:
        return self._romfs.data_files

    def _find(self, path: str) -> ROMFSFile | None:
        for f in self._data_files():
            if f.name == path:
                return f
        return None

    def _entry(self, file: ROMFSFile) -> Entry:
        return Entry(name=file.name, is_dir=False, length=file.length, path=file.name)

    def _require_writable(self) -> None:
        if not self._romfs.is_complete:
            raise ReadOnlyFilesystemError(
                "this ROM has no end marker — it is a fragment of a multi-ROM "
                "filing system (or a truncated image); ROMFS writes are refused"
            )
        if not self._romfs.is_plain:
            raise ReadOnlyFilesystemError(
                "this ROM carries code after the filing system (e.g. a *HELP "
                "handler or a language); ROMFS writes are refused to avoid "
                "corrupting it"
            )
        if not self._reader.writable:
            raise ReadOnlyFilesystemError("the image was opened read-only")

    def _commit(self, files: tuple[ROMFSFile, ...]) -> None:
        self._require_writable()
        rebuilt = self._romfs.with_files(files)
        image = rebuilt.to_bytes()  # may raise ROMFullError before any write
        self._reader.write(0, image)
        self._romfs = rebuilt

    # -- core Mount --
    def path_root(self) -> str:
        # ROMFS is flat: a nameless root holding the files as siblings.
        return ""

    def stat(self, path: str) -> Entry:
        if path == "":
            return Entry(name="", is_dir=True, length=0, path="")
        file = self._find(path)
        if file is None:
            raise ROMFSError(f"no file named {path!r}")
        return self._entry(file)

    def join(self, parent: str, name: str) -> str:
        return name

    def iter_entries(self, path: str) -> Iterable[Entry]:
        if path != "":
            raise ROMFSError(f"ROMFS is flat; {path!r} is not a directory")
        return [self._entry(f) for f in self._data_files()]

    def exists(self, path: str) -> bool:
        return path == "" or self._find(path) is not None

    def read_bytes(self, path: str) -> bytes:
        file = self._find(path)
        if file is None:
            raise ROMFSError(f"no file named {path!r}")
        return file.data

    def write_bytes(self, path: str, data: bytes) -> None:
        if not 1 <= len(path) <= MAX_NAME_LENGTH:
            raise ROMFSError(f"ROMFS file names are 1–{MAX_NAME_LENGTH} characters: {path!r}")
        existing = self._find(path)
        if existing is not None:
            replacement = ROMFSFile(
                path, existing.load_address, existing.exec_address, existing.run_only, bytes(data)
            )
            files = tuple(replacement if f is existing else f for f in self._romfs.files)
        else:
            files = self._romfs.files + (ROMFSFile(path, 0, 0, False, bytes(data)),)
        self._commit(files)

    def remove(self, path: str, *, force: bool = False) -> None:
        file = self._find(path)
        if file is None:
            raise ROMFSError(f"no file named {path!r}")
        # No lock gate: a ROMFS file's protection bit is *RUN-only copy
        # protection, not a delete-lock, and ROMFS has no delete-protection
        # concept at all (the medium is rebuilt wholesale). *force* is accepted
        # for the Mount contract but has nothing to override.
        self._commit(tuple(f for f in self._romfs.files if f is not file))

    def rename(self, old_path: str, new_path: str) -> None:
        file = self._find(old_path)
        if file is None:
            raise ROMFSError(f"no file named {old_path!r}")
        if not 1 <= len(new_path) <= MAX_NAME_LENGTH:
            raise ROMFSError(
                f"ROMFS file names are 1–{MAX_NAME_LENGTH} characters: {new_path!r}"
            )
        renamed = ROMFSFile(
            new_path, file.load_address, file.exec_address, file.run_only, file.data
        )
        self._commit(tuple(renamed if f is file else f for f in self._romfs.files))

    # -- StorageOrdered --
    def storage_key(self, path: str) -> int:
        # ROMFS stores its files sequentially in the ROM (a CFS block
        # stream), so a file's position in that stream is its storage
        # order — also the order *LOAD/*RUN reads them, there being no
        # seeks on a ROM.
        for index, file in enumerate(self._data_files()):
            if file.name == path:
                return index
        raise ROMFSError(f"no file named {path!r}")

    # -- AcornMetadata --
    def acorn_meta(self, path: str) -> AcornMeta:
        file = self._find(path)
        if file is None:
            raise ROMFSError(f"no file named {path!r}")
        access = Access.X if file.run_only else Access(0)
        return AcornMeta(
            load_address=file.load_address, exec_address=file.exec_address, access=int(access)
        )

    def set_acorn_meta(self, path: str, meta: AcornMeta) -> None:
        file = self._find(path)
        if file is None:
            raise ROMFSError(f"no file named {path!r}")
        load = file.load_address if meta.load_address is None else meta.load_address
        execa = file.exec_address if meta.exec_address is None else meta.exec_address
        # The run-only (copy-protection) bit is its own access axis, Access.X —
        # NOT the disc filing systems' delete-lock Access.L. Taking it only
        # from X means a ROMFS→ROMFS copy preserves it, while a locked DFS/ADFS
        # file imported here does not become *RUN-only (which would otherwise
        # make it unloadable: *EXEC / CHAIN would fail with "Locked").
        run_only = bool(meta.access & Access.X)
        updated = ROMFSFile(file.name, load, execa, run_only, file.data)
        self._commit(tuple(updated if f is file else f for f in self._romfs.files))

    # -- StatusReporting --
    def status_notes(self) -> tuple[str, ...]:
        if not self._romfs.is_complete:
            return ("incomplete — appears to be a fragment of a multi-ROM set (read-only)",)
        if not self._romfs.is_plain:
            return ("composite — carries code after the filing system (read-only)",)
        return ()

    # -- Titled --
    @property
    def title(self) -> str:
        return self._romfs.title

    def set_title(self, title: str) -> None:
        wrapped = f"*{title}*"
        if len(wrapped) > MAX_NAME_LENGTH:
            raise ROMFSError(
                f"ROMFS title is too long: {title!r} would not fit in "
                f"{MAX_NAME_LENGTH} characters once wrapped in asterisks"
            )
        title_block = ROMFSFile(wrapped, 0, 0, True, b"")
        files = self._romfs.files
        if self._romfs.title_block is not None:
            files = (title_block,) + files[1:]
        else:
            files = (title_block,) + files
        self._commit(files)


class AcornROMFS(Filesystem):
    """Acorn ROM Filing System — the cassette filing system on a paged ROM.

    The filing system used by BBC Micro and Acorn Electron sideways ROMs and
    cartridges. Files are stored in Cassette Filing System block format with
    Acorn load/exec addresses and a lock bit; the medium is read-only ROM,
    so the filing system is flat (no directories). Up to a 16 KiB image.
    """

    extensions = _EXTENSIONS
    #: ROMFS is the default creator for `.rom` images.
    creates = _EXTENSIONS

    def __init__(self, name: str = "acorn-romfs", **kwargs):
        super().__init__(name=name, **kwargs)

    def probe(self, reader: ImageReader) -> Identification | None:
        try:
            romfs = ROMFS.from_bytes(reader.read(0, reader.size))
        except (NotAROMFSError, CRCError, TruncatedROMError):
            return None

        data_files = romfs.data_files
        evidence = [
            f"ROM type &{romfs.rom_type:02X}"
            + (" (service entry)" if romfs.has_service_entry else ""),
            f"copyright {romfs.copyright!r}",
            f"{len(data_files)} file(s), all block CRCs valid",
        ]
        if romfs.title:
            evidence.append(f"title {romfs.title!r}")
        # A CRC-validated block chain plus an Acorn (C) copyright string is a
        # strong, integrity-checked match; without the copyright it is merely
        # a well-formed chain. An image with no end marker is incomplete — a
        # fragment of a multi-ROM filing system, or truncated — so it is
        # demoted and flagged: it is identified and read, but never written.
        confident = romfs.has_service_entry and romfs.copyright.startswith("(C)")
        if not romfs.is_complete:
            evidence.append("no end marker — incomplete (multi-ROM fragment?); read-only")
        confidence = (
            Confidence.STRONG if (confident and romfs.is_complete) else Confidence.PROBABLE
        )
        return Identification(
            filesystem=self.name,
            confidence=confidence,
            evidence=tuple(evidence),
            geometry=_linear_geometry(reader.size),
        )

    def open(self, reader: ImageReader, geometry: Geometry, *, surface: int = 0) -> _ROMFSMount:
        romfs = ROMFS.from_bytes(reader.read(0, reader.size))
        return _ROMFSMount(romfs, reader)

    def geometry_grammar(self) -> GeometryGrammar:
        return GeometryGrammar(presets=dict(_GEOMETRY_PRESETS), kinds=())

    def default_geometry(self, suffix: str) -> Geometry | None:
        # A paged ROM is conventionally 16 KiB; 8 KiB is offered as a preset.
        return _GEOMETRY_PRESETS["16k"] if suffix.lower() == ".rom" else None

    def create(self, filepath, geometry: Geometry, *, title: str) -> None:
        # The title block is stored as `*title*`, so it is capped shorter than
        # a full CFS name; fall back to the file's stem, and truncate.
        name = (title or filepath.stem)[:MAX_TITLE_LENGTH] or "ROMFS"
        image = build_rom_image(title=name, size=geometry.image_size)
        filepath.write_bytes(image)

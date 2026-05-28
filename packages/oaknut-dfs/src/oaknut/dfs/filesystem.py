"""DFS-family filesystems as oaknut.filesystem extensions.

Acorn DFS and Watford DFS are *peer* filesystems that share this
package's flat-catalogue implementation. Each is registered on the
``oaknut.filesystem`` axis (see ``pyproject.toml``); this module adapts
the existing :class:`~oaknut.dfs.DFS` class to the
:class:`~oaknut.filesystem.Filesystem` contract — detection via the
catalogue heuristics, a :class:`~oaknut.filesystem.Mount` over the DFS
API, and the floppy geometry grammar.

Part of Phase B of the filesystem-extensibility refactor: a thin
adapter over the proven class, to be refactored inward later.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut.dfs.dfs import DFS
from oaknut.dfs.watford_dfs_catalogue import WatfordDFSCatalogue
from oaknut.discimage import BYTES_PER_SECTOR, DiscFormat, DiscImage, SurfaceSpec
from oaknut.file import AcornMeta
from oaknut.filesystem import (
    FLOPPY,
    Confidence,
    Entry,
    Filesystem,
    Geometry,
    GeometryGrammar,
    Identification,
    ImageReader,
    floppy_geometry,
)

# An Acorn/Watford catalogue lives in sectors 0–3; matching needs them.
_MIN_SECTORS = 4

# Named floppy geometry presets the DFS filesystems offer.
_GEOMETRY_PRESETS = {
    "40t-ss": floppy_geometry(tracks=40, sides=1, label="40-track single-sided"),
    "80t-ss": floppy_geometry(tracks=80, sides=1, label="80-track single-sided"),
    "40t-ds": floppy_geometry(tracks=40, sides=2, label="40-track double-sided"),
    "80t-ds": floppy_geometry(tracks=80, sides=2, label="80-track double-sided"),
}


def _flat_surface(reader: ImageReader):
    """A single linear surface over the whole region for catalogue matching.

    DFS catalogue sectors sit at fixed low offsets regardless of the true
    track geometry, so a flat surface lets the catalogue heuristics run
    unchanged.
    """
    sectors = reader.size // BYTES_PER_SECTOR
    if sectors < _MIN_SECTORS:
        return None
    data = reader.read(0, sectors * BYTES_PER_SECTOR)
    buffer = memoryview(bytearray(data))
    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=sectors,
        bytes_per_sector=BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=sectors * BYTES_PER_SECTOR,
    )
    return DiscImage(buffer, [spec]).surface(0)


def _propose_geometry(size: int) -> tuple[Geometry | None, tuple[Geometry, ...]]:
    """Best-guess geometry from image size, plus byte-identical alternatives.

    Sidedness/interleave cannot be read from the bytes: an 80-track
    single-sided image and a 40-track double-sided one are the same
    length, so the latter is reported as an *ambiguity*.
    """
    if size == _GEOMETRY_PRESETS["40t-ss"].image_size:
        return _GEOMETRY_PRESETS["40t-ss"], ()
    if size == _GEOMETRY_PRESETS["80t-ss"].image_size:
        return _GEOMETRY_PRESETS["80t-ss"], (_GEOMETRY_PRESETS["40t-ds"],)
    if size == _GEOMETRY_PRESETS["80t-ds"].image_size:
        return _GEOMETRY_PRESETS["80t-ds"], ()
    if size > 0 and size % BYTES_PER_SECTOR == 0:
        sectors = size // BYTES_PER_SECTOR
        spec = SurfaceSpec(1, sectors, BYTES_PER_SECTOR, 0, size)
        return Geometry((spec,), label=f"{sectors} sectors, single-sided"), ()
    return None, ()


class _DFSMount:
    """A :class:`~oaknut.filesystem.Mount` over a :class:`DFS` instance.

    Implements the core plus ``AcornMetadata``, ``Titled``, ``Bootable``
    and ``FreeSpace``; DFS
    is flat (a fixed root/letter/file shape), so it does *not* advertise
    ``HierarchicalDirectories``.
    """

    def __init__(self, dfs: DFS):
        self._dfs = dfs

    def path_root(self) -> str:
        # DFS has a *nameless* virtual root holding the populated
        # directory letters ($, A, B, …) as siblings; $ is just the
        # default one, not the root. So the root path is the empty
        # string — a bare ``ls`` lists the directory letters, and
        # ``:$`` drills into the default directory's files.
        return ""

    def _navigate(self, path: str):
        return self._dfs.path(path)

    def stat(self, path: str) -> Entry:
        target = self._navigate(path)
        st = target.stat()
        return Entry(name=target.name, is_dir=st.is_directory, length=st.length, path=target.path)

    def join(self, parent: str, name: str) -> str:
        # DFS's root is the nameless catalogue; a file placed there lives
        # in the default $ directory. Qualify it as $.NAME so write and
        # lookup agree (a bare "NAME" writes to $ but doesn't resolve back).
        if parent == "":
            return f"$.{name}"
        return (self._navigate(parent) / name).path

    def iter_entries(self, path: str) -> Iterable[Entry]:
        for child in self._navigate(path).iterdir():
            st = child.stat()
            yield Entry(name=child.name, is_dir=st.is_directory, length=st.length, path=child.path)

    def exists(self, path: str) -> bool:
        return self._navigate(path).exists()

    def read_bytes(self, path: str) -> bytes:
        return self._navigate(path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        self._navigate(path).write_bytes(data)

    def remove(self, path: str, *, force: bool = False) -> None:
        from oaknut.dfs.exceptions import FileLocked

        target = self._navigate(path)
        # DFS directories are letter prefixes with no entry of their own;
        # they vanish once their files are gone, so removing one is a no-op.
        if target.is_dir():
            return
        try:
            target.unlink()
        except FileLocked:
            if not force:
                raise
            target.unlock()
            target.unlink()

    def rename(self, old_path: str, new_path: str) -> None:
        self._navigate(old_path).rename(new_path)

    # -- AcornMetadata --
    def acorn_meta(self, path: str) -> AcornMeta:
        stat = self._navigate(path).stat()
        return AcornMeta(
            load_address=stat.load_address,
            exec_address=stat.exec_address,
            access=int(stat.access),
        )

    def set_acorn_meta(self, path: str, meta: AcornMeta) -> None:
        from oaknut.file import Access

        target = self._navigate(path)
        if meta.load_address is not None:
            target.set_load_address(meta.load_address)
        if meta.exec_address is not None:
            target.set_exec_address(meta.exec_address)
        # DFS records only the lock bit; the other access flags have no
        # representation in its catalogue.
        if meta.access & Access.L:
            target.lock()
        else:
            target.unlock()

    # -- Titled / Bootable --
    @property
    def title(self) -> str:
        return self._dfs.title

    def set_title(self, title: str) -> None:
        self._dfs.title = title

    @property
    def boot_option(self):
        return self._dfs.boot_option

    def set_boot_option(self, option) -> None:
        self._dfs.boot_option = option

    # -- FreeSpace --
    def free_bytes(self) -> int:
        return self._dfs.free_sectors * 256

    # -- Sized --
    def size_bytes(self) -> int:
        return self._dfs.info["total_sectors"] * 256

    # -- FreeMap --
    def free_map(self):
        from oaknut.filesystem import FreeMapData

        surface = self._dfs._catalogued_surface
        regions = tuple(surface.get_free_map())  # already (start, length) in sectors
        total = surface.catalogue.get_disc_info().total_sectors
        return FreeMapData(free_regions=regions, total_sectors=total)

    # -- Compactable --
    def compact(self) -> int:
        return self._dfs.compact()

    # -- Validatable --
    def validate(self) -> list:
        return self._dfs.validate()


class _BaseDFS(Filesystem):
    """Shared behaviour for the flat-catalogue DFS-family filesystems."""

    extensions = frozenset({".ssd", ".dsd"})

    #: The concrete catalogue class (subclass responsibility).
    _catalogue: type = AcornDFSCatalogue
    _confidence: Confidence = Confidence.PROBABLE
    _evidence: str = ""

    def probe(self, reader: ImageReader) -> Identification | None:
        surface = _flat_surface(reader)
        if surface is None or not self._catalogue.matches(surface):
            return None
        geometry, ambiguities = _propose_geometry(reader.size)
        return Identification(
            filesystem=self.name,
            confidence=self._confidence,
            evidence=(self._evidence,),
            geometry=geometry,
            ambiguities=ambiguities,
        )

    def open(self, reader: ImageReader, geometry: Geometry) -> _DFSMount:
        disc_format = DiscFormat(
            surface_specs=list(geometry.surface_specs),
            catalogue_name=self._catalogue.CATALOGUE_NAME,
        )
        # Building over the reader's buffer() means mutations persist to
        # the file when the reader is writable, and run against a private
        # copy when it is not.
        return _DFSMount(DFS.from_buffer(reader.buffer(), disc_format))

    def geometry_grammar(self) -> GeometryGrammar:
        return GeometryGrammar(presets=dict(_GEOMETRY_PRESETS), kinds=(FLOPPY,))

    def default_geometry(self, suffix: str) -> Geometry | None:
        # The conventional 80-track shapes; .ssd single-sided, .dsd double.
        return {
            ".ssd": _GEOMETRY_PRESETS["80t-ss"],
            ".dsd": _GEOMETRY_PRESETS["80t-ds"],
        }.get(suffix.lower())

    def create(self, filepath, geometry: Geometry, *, title: str) -> None:
        disc_format = DiscFormat(
            surface_specs=list(geometry.surface_specs),
            catalogue_name=self._catalogue.CATALOGUE_NAME,
        )
        with DFS.create_file(filepath, disc_format, title=title):
            pass


class AcornDFS(_BaseDFS):
    """Acorn DFS — the standard flat-catalogue BBC floppy format.

    Up to 31 named files, each in one of 27 sibling directories
    ($ and A–Z). Directories are managed automatically: created when the
    first file is added and deleted when the last file is removed.
    """

    _catalogue = AcornDFSCatalogue
    _confidence = Confidence.PROBABLE
    _evidence = "well-formed Acorn DFS catalogue in sectors 0–1"
    #: The default creator for plain DFS floppies.
    creates = frozenset({".ssd", ".dsd"})


class WatfordDFS(_BaseDFS):
    """Watford DFS — the 62-file extended-catalogue BBC floppy format.

    Up to 62 named files, each in one of 27 sibling directories
    ($ and A–Z). Directories are managed automatically: created when the
    first file is added and deleted when the last file is removed.
    """

    _catalogue = WatfordDFSCatalogue
    _confidence = Confidence.STRONG
    _evidence = "Watford DFS extended catalogue (0xAA marker, synced metadata)"
    priority = 10

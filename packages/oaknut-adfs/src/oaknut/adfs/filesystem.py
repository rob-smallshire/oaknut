"""ADFS as an oaknut.filesystem extension.

Adapts the existing :class:`~oaknut.adfs.ADFS` class to the
:class:`~oaknut.filesystem.Filesystem` contract. ADFS hosts a *reserved
tail* region (where an AFS or DRDOS-FAT filesystem may live), which it
exposes generically via :class:`~oaknut.filesystem.RegionHost` and in
:meth:`probe`'s ``reserved_regions`` — computed from ADFS's *own*
old-map extent, with no knowledge of what occupies the tail. The
coordinator recurses into it.

Part of Phase B of the filesystem-extensibility refactor.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.adfs.adfs import ADFS as _ADFSDisc
from oaknut.adfs.free_space_map import _calculate_old_map_checksum
from oaknut.discimage import BYTES_PER_SECTOR
from oaknut.file import AcornMeta
from oaknut.filesystem import (
    FLOPPY,
    WINCHESTER,
    Confidence,
    Entry,
    Filesystem,
    FilesystemError,
    Geometry,
    GeometryGrammar,
    Identification,
    ImageReader,
    Partition,
    floppy_geometry,
)

# The old free-space map occupies sectors 0–1.
_MAP_BYTES = 512

# ADFS floppy geometries use 16 sectors per track.
_ADFS_PRESETS = {
    "s": floppy_geometry(tracks=40, sides=1, sectors_per_track=16, label="ADFS S (40T SS)"),
    "m": floppy_geometry(tracks=80, sides=1, sectors_per_track=16, label="ADFS M (80T SS)"),
    "l": floppy_geometry(tracks=80, sides=2, sectors_per_track=16, label="ADFS L (80T DS)"),
}


def _propose_geometry(size: int) -> Geometry | None:
    """The floppy geometry matching *size*, or None for a hard disc.

    Hard-disc geometry (cylinders/heads/SPT) is not derivable from the
    image alone — it needs the ``.dsc`` sidecar — so it is left
    unresolved here.
    """
    for geometry in _ADFS_PRESETS.values():
        if size == geometry.image_size:
            return geometry
    return None


# The old map records a reserved-tail info-sector pointer at &F6 of
# sector 0 (the gap after the 82-entry free-start table). It is the
# logical sector of the tail filesystem's info sector; the region
# begins one sector before it. Zero on a disc with no reserved tail.
# This is ADFS's own reservation record — read without interpreting
# what occupies the region (AFS, DRDOS-FAT, …). Works for both a hard
# disc (tail beyond the ADFS extent) and a floppy (tail carved within).
_RESERVED_TAIL_POINTER_OFFSET = 0xF6


def _reserved_regions(reader: ImageReader) -> tuple[Partition, ...]:
    """The tail region ADFS reserves for another filesystem, in logical sectors."""
    sector0 = reader.read(0, BYTES_PER_SECTOR)
    if len(sector0) < BYTES_PER_SECTOR:
        return ()
    pointer = int.from_bytes(
        sector0[_RESERVED_TAIL_POINTER_OFFSET : _RESERVED_TAIL_POINTER_OFFSET + 4],
        "little",
    )
    if pointer <= 0:
        return ()
    start_sector = pointer - 1
    total_sectors = reader.size // BYTES_PER_SECTOR
    if 0 < start_sector < total_sectors:
        return (Partition("", start_sector, total_sectors - start_sector),)
    return ()


class _ADFSMount:
    """A :class:`~oaknut.filesystem.Mount` over an :class:`ADFS` instance.

    Implements the core plus ``HierarchicalDirectories``, ``AcornMetadata``,
    ``Titled``, ``Bootable``, ``FreeSpace`` and ``RegionHost``.
    """

    def __init__(
        self,
        adfs: _ADFSDisc,
        reserved: tuple[Partition, ...],
        geometry: "Geometry | None" = None,
    ):
        self._adfs = adfs
        self._reserved = reserved
        # The geometry the disc was opened with — carries hard-disc CHS
        # from a .dsc sidecar that the content alone cannot supply.
        self._geometry = geometry

    def path_root(self) -> str:
        return "$"

    def _navigate(self, path: str):
        return self._adfs.path(path)

    def stat(self, path: str) -> Entry:
        target = self._navigate(path)
        st = target.stat()
        return Entry(
            name=target.name, is_dir=st.is_directory, length=st.length, path=target.path
        )

    def join(self, parent: str, name: str) -> str:
        return (self._navigate(parent) / name).path

    def iter_entries(self, path: str) -> Iterable[Entry]:
        for child in self._navigate(path).iterdir():
            st = child.stat()
            yield Entry(
                name=child.name, is_dir=st.is_directory, length=st.length, path=child.path
            )

    def exists(self, path: str) -> bool:
        return self._navigate(path).exists()

    def read_bytes(self, path: str) -> bytes:
        return self._navigate(path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        self._navigate(path).write_bytes(data)

    def remove(self, path: str, *, force: bool = False) -> None:
        from oaknut.adfs.exceptions import ADFSFileLockedError

        target = self._navigate(path)
        delete = target.rmdir if target.is_dir() else target.unlink
        try:
            delete()
        except ADFSFileLockedError:
            if not force:
                raise
            target.unlock()
            delete()

    def rename(self, old_path: str, new_path: str) -> None:
        self._navigate(old_path).rename(new_path)

    # -- HierarchicalDirectories --
    def make_directory(
        self,
        path: str,
        *,
        parents: bool = False,
        exist_ok: bool = False,
        title: str | None = None,
    ) -> None:
        target = self._navigate(path)
        target.mkdir(parents=parents, exist_ok=exist_ok)
        # ADFS directories carry a title.
        if title is not None:
            target.title = title

    # -- AcornMetadata --
    def acorn_meta(self, path: str) -> AcornMeta:
        stat = self._navigate(path).stat()
        return AcornMeta(
            load_address=stat.load_address,
            exec_address=stat.exec_address,
            access=int(stat.access),
        )

    def set_acorn_meta(self, path: str, meta: AcornMeta) -> None:
        target = self._navigate(path)
        if meta.load_address is not None:
            target.set_load_address(meta.load_address)
        if meta.exec_address is not None:
            target.set_exec_address(meta.exec_address)
        target.chmod(int(meta.access))

    # -- Titled / Bootable --
    @property
    def title(self) -> str:
        return self._adfs.title

    def set_title(self, title: str) -> None:
        self._adfs.title = title

    # -- DirectoryTitled --
    def directory_title(self, path: str) -> str:
        return self._navigate(path).title

    def set_directory_title(self, path: str, title: str) -> None:
        self._navigate(path).title = title

    @property
    def boot_option(self):
        return self._adfs.boot_option

    def set_boot_option(self, option) -> None:
        self._adfs.boot_option = option

    # -- FreeSpace --
    def free_bytes(self) -> int:
        return self._adfs.free_space

    # -- Sized --
    def size_bytes(self) -> int:
        # The ADFS slice — excludes any reserved AFS tail — so partition
        # sizes sum to the whole disc.
        return self._adfs.total_size

    # -- PhysicalGeometry --
    def disc_geometry(self):
        from oaknut.filesystem import DiscGeometry

        # A hard disc carries its CHS only in the .dsc sidecar, surfaced
        # through the opened geometry; a floppy's CHS is implied by its
        # size and recorded on the disc itself.
        opened = self._geometry
        if opened is not None and opened.cylinders is not None:
            cylinders, heads, spt = (
                opened.cylinders,
                opened.heads,
                opened.sectors_per_track,
            )
        else:
            geom = self._adfs.geometry
            cylinders, heads, spt = geom.cylinders, geom.heads, geom.sectors_per_track
        return DiscGeometry(
            label=f"{cylinders} cylinders × {heads} heads × {spt} sectors/track",
            sectors_per_cylinder=heads * spt,
            total_sectors=cylinders * heads * spt,
        )

    # -- FreeMap --
    def free_map(self):
        from oaknut.filesystem import FreeMapData

        fsm = self._adfs._fsm
        regions = tuple(
            (start // 256, length // 256) for start, length in fsm.free_space_entries()
        )
        return FreeMapData(free_regions=regions, total_sectors=fsm.total_sectors)

    # -- Compactable --
    def compact(self) -> int:
        return self._adfs.compact()

    # -- Validatable --
    def validate(self) -> list:
        return self._adfs.validate()

    # -- RegionHost --
    def reserved_regions(self) -> tuple[Partition, ...]:
        return self._reserved


class ADFS(Filesystem):
    """ADFS — Acorn's hierarchical filing system (floppies and hard discs).

    Detects the old-map layout by its root-directory signature (``Hugo``
    at 0x201, ``Nick`` at 0x401), corroborated by the free-space-map
    checksums. A reserved tail region — where an AFS (Level 3 File
    Server) or DRDOS FAT filesystem may live — is reported for the
    coordinator to recurse into; ADFS itself stays ignorant of it.
    """

    extensions = frozenset({".adf", ".ads", ".adm", ".adl", ".dat"})
    #: ADFS is the default creator for all its extensions, including the
    #: hard-disc .dat (AFS, which also reads .dat, is made inside an ADFS
    #: disc by afs-init, not by `disc create`).
    creates = frozenset({".adf", ".ads", ".adm", ".adl", ".dat"})

    def probe(self, reader: ImageReader) -> Identification | None:
        sectors = reader.read(0, _MAP_BYTES)
        if len(sectors) < _MAP_BYTES:
            return None
        has_hugo = reader.read(0x201, 4) == b"Hugo"
        has_nick = reader.read(0x401, 4) == b"Nick"
        if not (has_hugo or has_nick):
            return None

        map_valid = (
            _calculate_old_map_checksum(sectors, 0) == sectors[0xFF]
            and _calculate_old_map_checksum(sectors, 0x100) == sectors[0x1FF]
        )
        evidence = [
            "old-format root directory ('Hugo')"
            if has_hugo
            else "new-format root directory ('Nick')"
        ]
        if map_valid:
            evidence.append("old-map free-space-map checksums valid")

        return Identification(
            filesystem=self.name,
            confidence=Confidence.STRONG if map_valid else Confidence.PROBABLE,
            evidence=tuple(evidence),
            geometry=_propose_geometry(reader.size),
            reserved_regions=_reserved_regions(reader),
        )

    def open(self, reader: ImageReader, geometry: Geometry | None = None) -> _ADFSMount:
        # ADFS addresses sectors linearly, so the disc reads correctly from
        # the buffer regardless of geometry; the geometry is retained so
        # the mount can *report* the hard-disc CHS a .dsc sidecar supplies.
        # Building over the reader's buffer() means mutations persist to the
        # file when the reader is writable, and run against a private copy
        # when it is not.
        return _ADFSMount(
            _ADFSDisc.from_buffer(reader.buffer()), _reserved_regions(reader), geometry
        )

    def geometry_grammar(self) -> GeometryGrammar:
        return GeometryGrammar(presets=dict(_ADFS_PRESETS), kinds=(FLOPPY, WINCHESTER))

    def default_geometry(self, suffix: str) -> Geometry | None:
        # The single-shape floppy extensions map to their preset; .adf is
        # ambiguous (S or M) and .dat is an open-ended hard disc, so both
        # need an explicit --geometry.
        return {
            ".ads": _ADFS_PRESETS["s"],
            ".adm": _ADFS_PRESETS["m"],
            ".adl": _ADFS_PRESETS["l"],
        }.get(suffix.lower())

    def create(self, filepath, geometry: Geometry, *, title: str) -> None:
        from oaknut.adfs import ADFS_L, ADFS_M, ADFS_S

        if geometry.cylinders is not None:
            # Hard disc: create from the CHS the geometry carries.
            with _ADFSDisc.create_file(
                filepath,
                cylinders=geometry.cylinders,
                heads=geometry.heads,
                sectors_per_track=geometry.sectors_per_track,
                title=title,
            ):
                pass
            return
        # Floppy: match the geometry's size to a named ADFS format.
        by_size = {fmt.total_bytes: fmt for fmt in (ADFS_S, ADFS_M, ADFS_L)}
        adfs_format = by_size.get(geometry.image_size)
        if adfs_format is None:
            raise FilesystemError(
                f"no ADFS floppy format for a {geometry.image_size}-byte image"
            )
        with _ADFSDisc.create_file(filepath, adfs_format, title=title):
            pass

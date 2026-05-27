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


def _reserved_regions(reader: ImageReader) -> tuple[Partition, ...]:
    """The tail region ADFS reserves beyond its own extent, if any.

    ADFS records its own size in the old map (total sectors at
    0xFC–0xFE). When the image is larger, the excess tail is a reserved
    region another filesystem occupies — found here without knowing
    which, so ADFS stays ignorant of AFS/FAT.
    """
    sector0 = reader.read(0, BYTES_PER_SECTOR)
    if len(sector0) < BYTES_PER_SECTOR:
        return ()
    total_sectors = sector0[0xFC] | (sector0[0xFD] << 8) | (sector0[0xFE] << 16)
    reserved_offset = total_sectors * BYTES_PER_SECTOR
    if 0 < reserved_offset < reader.size:
        return (Partition("", reserved_offset, reader.size - reserved_offset),)
    return ()


class _ADFSMount:
    """A :class:`~oaknut.filesystem.Mount` over an :class:`ADFS` instance.

    Implements the core plus ``HierarchicalDirectories``, ``AcornMetadata``,
    ``DiscMetadata`` and ``RegionHost``.
    """

    def __init__(self, adfs: _ADFSDisc, reserved: tuple[Partition, ...]):
        self._adfs = adfs
        self._reserved = reserved

    def path_root(self) -> str:
        return "$"

    def _navigate(self, path: str):
        return self._adfs.path(path)

    def iter_entries(self, path: str) -> Iterable[Entry]:
        for child in self._navigate(path).iterdir():
            stat = child.stat()
            yield Entry(name=child.name, is_dir=stat.is_directory, length=stat.length)

    def exists(self, path: str) -> bool:
        return self._navigate(path).exists()

    def read_bytes(self, path: str) -> bytes:
        return self._navigate(path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        self._navigate(path).write_bytes(data)

    # -- HierarchicalDirectories --
    def make_directory(self, path: str) -> None:
        self._navigate(path).mkdir()

    # -- AcornMetadata --
    def acorn_meta(self, path: str) -> AcornMeta:
        stat = self._navigate(path).stat()
        return AcornMeta(
            load_address=stat.load_address,
            exec_address=stat.exec_address,
            access=int(stat.access),
        )

    def set_acorn_meta(self, path: str, meta: AcornMeta) -> None:  # pragma: no cover
        raise NotImplementedError("ADFS metadata write-back is wired in Phase C")

    # -- DiscMetadata --
    @property
    def title(self) -> str:
        return self._adfs.title

    @property
    def boot_option(self):
        return self._adfs.boot_option

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
        # ADFS determines its own geometry from image size, so the
        # geometry argument is advisory here.
        buffer = memoryview(bytearray(reader.read(0, reader.size)))
        return _ADFSMount(_ADFSDisc.from_buffer(buffer), _reserved_regions(reader))

    def geometry_grammar(self) -> GeometryGrammar:
        return GeometryGrammar(presets=dict(_ADFS_PRESETS), kinds=(FLOPPY, WINCHESTER))

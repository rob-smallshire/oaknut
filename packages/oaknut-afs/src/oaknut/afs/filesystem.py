"""AFS as an oaknut.filesystem extension.

The Acorn Level 3 File Server region is found by the coordinator
*recursing* into the reserved tail an ADFS host exposes: this filesystem
is handed a window over that region, not the whole disc. AFS on-disc
addresses are absolute physical-disc sectors, so the underlying AFS
class is mounted with a ``region_base`` (the window's absolute start =
``start_cylinder * sectors_per_cylinder``) that it subtracts at the
disc-access chokepoints — letting the same class serve both a
whole-disc open (base 0) and this windowed one.

Part of Phase B of the filesystem-extensibility refactor.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.afs.afs import AFS as _AFSRegion
from oaknut.afs.exceptions import AFSInfoSectorError
from oaknut.afs.info_sector import INFO_SECTOR_SIZE, MAGIC, InfoSector
from oaknut.discimage import BYTES_PER_SECTOR, DiscImage, SurfaceSpec, UnifiedDisc
from oaknut.file import AcornMeta
from oaknut.filesystem import (
    WINCHESTER,
    Confidence,
    Entry,
    Filesystem,
    FilesystemError,
    Geometry,
    GeometryGrammar,
    Identification,
    ImageReader,
)

# The info sector sits at sector 1 of the AFS region (start_cylinder*spc
# + 1). The coordinator hands AFS a window starting at the region base,
# so the info sector is at this fixed offset. Requiring it here means AFS
# matches only a region-aligned window — never the whole disc, where this
# offset holds the ADFS map — so AFS is a tail filesystem, not a top-level one.
_INFO_SECTOR_OFFSET = INFO_SECTOR_SIZE


def _read_info(reader: ImageReader) -> InfoSector | None:
    """The AFS info sector at the region's sector 1, or None if not AFS."""
    sector = reader.read(_INFO_SECTOR_OFFSET, INFO_SECTOR_SIZE)
    if sector[:4] != MAGIC:
        return None
    try:
        return InfoSector.from_bytes(sector)
    except (AFSInfoSectorError, ValueError):
        return None


def _window_disc(reader: ImageReader) -> UnifiedDisc:
    """A UnifiedDisc over the whole region in *reader*, as linear sectors."""
    sectors = reader.size // BYTES_PER_SECTOR
    buffer = memoryview(bytearray(reader.read(0, sectors * BYTES_PER_SECTOR)))
    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=sectors,
        bytes_per_sector=BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=sectors * BYTES_PER_SECTOR,
    )
    return UnifiedDisc(DiscImage(buffer, [spec]))


class _AFSMount:
    """A :class:`~oaknut.filesystem.Mount` over an AFS region.

    Implements the core plus ``HierarchicalDirectories``,
    ``AcornMetadata`` and ``UserDatabase``.
    """

    def __init__(self, afs: _AFSRegion):
        self._afs = afs

    def path_root(self) -> str:
        return "$"

    def _navigate(self, path: str):
        root = self._afs.root
        stripped = path.strip()
        if stripped in ("", "$"):
            return root
        if stripped.startswith("$."):
            stripped = stripped[2:]
        target = root
        for component in stripped.split("."):
            if component:
                target = target / component
        return target

    def _is_root(self, path: str) -> bool:
        return path.strip() in ("", "$")

    def stat(self, path: str) -> Entry:
        if self._is_root(path):
            return Entry(name="$", is_dir=True, length=0, path="$")
        target = self._navigate(path)
        st = target.stat()
        return Entry(
            name=st.name, is_dir=st.is_directory, length=st.length, path=target.path
        )

    def iter_entries(self, path: str) -> Iterable[Entry]:
        for child in self._navigate(path).iterdir():
            st = child.stat()
            yield Entry(
                name=st.name, is_dir=st.is_directory, length=st.length, path=child.path
            )

    def exists(self, path: str) -> bool:
        return self._is_root(path) or self._navigate(path).exists()

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
        raise NotImplementedError("AFS metadata write-back is wired in Phase C")

    # -- Titled --
    @property
    def title(self) -> str:
        return self._afs.title

    # -- FreeSpace --
    def free_bytes(self) -> int:
        return self._afs.free_sectors * 256

    # -- UserDatabase --
    def user_names(self) -> tuple[str, ...]:
        return tuple(record.full_id for record in self._afs.users)


class AFS(Filesystem):
    """AFS — the Acorn Level 3 File Server's private on-disc format.

    Recognised by the ``AFS0`` info sector in the tail region of an ADFS
    hard disc, with a redundant second copy one cylinder on. The
    coordinator finds it by recursing into the region ADFS reserves, so
    this filesystem operates on a window of just that region.
    """

    extensions = frozenset({".dat"})

    def probe(self, reader: ImageReader) -> Identification | None:
        info = _read_info(reader)
        if info is None:
            return None
        spc = info.sectors_per_cylinder
        verified = (
            spc > 0
            and reader.read((1 + spc) * INFO_SECTOR_SIZE, INFO_SECTOR_SIZE)
            == reader.read(_INFO_SECTOR_OFFSET, INFO_SECTOR_SIZE)
        )
        evidence = [f"AFS0 info sector (disc {info.disc_name!r})"]
        evidence.append("redundant copy verified" if verified else "single info-sector copy")
        return Identification(
            filesystem=self.name,
            confidence=Confidence.CERTAIN if verified else Confidence.STRONG,
            evidence=tuple(evidence),
        )

    def open(self, reader: ImageReader, geometry: Geometry | None = None) -> _AFSMount:
        info = _read_info(reader)
        if info is None:
            raise FilesystemError("no AFS info sector found in this region")
        spc = info.sectors_per_cylinder
        # On-disc addresses are absolute physical-disc sectors; the window
        # starts at the region base (start_cylinder * spc), which AFS
        # subtracts. The info sector is at region sector 1.
        region_base = info.start_cylinder * spc
        sec1 = region_base + 1
        sec2 = sec1 + spc
        return _AFSMount(
            _AFSRegion(_window_disc(reader), sec1, sec2, region_base=region_base)
        )

    def geometry_grammar(self) -> GeometryGrammar:
        # AFS geometry is dictated by its host, not independently chosen.
        return GeometryGrammar(kinds=(WINCHESTER,))

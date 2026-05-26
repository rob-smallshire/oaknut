"""Content-based probers for the DFS family, plugged into oaknut.identify.

Registered under the ``oaknut.prober`` entry-point namespace (see this
package's ``pyproject.toml``), so the detector ships with the format it
detects and joins the identification cascade automatically.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut.dfs.watford_dfs_catalogue import WatfordDFSCatalogue
from oaknut.discimage import BYTES_PER_SECTOR, DiscImage, SurfaceSpec
from oaknut.identify import Confidence, Identification, ImageReader, Prober

#: An Acorn DFS catalogue occupies sectors 0–1; identifying it (and
#: excluding Watford DDFS) needs to inspect through sector 3.
_MIN_SECTORS = 4


def _flat_surface(reader: ImageReader):
    """Build a single linear surface spanning the whole image.

    DFS catalogue sectors live at fixed low offsets regardless of the
    true track geometry, so a flat surface is all the catalogue
    heuristic needs — and it lets us reuse
    :meth:`AcornDFSCatalogue.matches` verbatim rather than duplicating
    its byte-level checks.
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


class AcornDFSProber(Prober):
    """Acorn DFS — the standard flat-catalogue BBC/Electron floppy format.

    Recognises the two-sector catalogue at the start of a side: a
    well-formed title, a file count that is a multiple of eight and
    within range, and a total-sector field that is plausible and
    divisible by the ten sectors per DFS track. Watford DDFS, which
    shares the same opening layout, is excluded by its extended-catalogue
    markers in sectors 2–3.

    The catalogue does not record sidedness or track count
    unambiguously, and interleaved and sequential double-sided images are
    byte-identical, so this prober reports the *family* with PROBABLE
    confidence and leaves the concrete geometry to be resolved elsewhere.
    """

    family = "dfs"
    extensions = frozenset({".ssd", ".dsd"})

    def probe(self, reader: ImageReader) -> Iterable[Identification]:
        surface = _flat_surface(reader)
        if surface is None or not AcornDFSCatalogue.matches(surface):
            return ()
        total_sectors = self._total_sectors(reader)
        evidence = (
            "well-formed Acorn DFS catalogue in sectors 0–1 "
            f"(total sectors = {total_sectors})",
        )
        return (
            Identification(
                prober_name=self.name,
                family=self.family,
                confidence=Confidence.PROBABLE,
                evidence=evidence,
            ),
        )

    @staticmethod
    def _total_sectors(reader: ImageReader) -> int:
        """The catalogue's declared total sector count (10-bit, sector 1)."""
        sector1 = reader.read(BYTES_PER_SECTOR, BYTES_PER_SECTOR)
        if len(sector1) < 8:
            return 0
        return ((sector1[6] & 0x03) << 8) | sector1[7]


class WatfordDFSProber(Prober):
    """Watford DDFS — the 62-file extended-catalogue BBC floppy format.

    Watford reuses Acorn's opening two sectors but adds a second
    catalogue in sectors 2–3, marked by twelve ``0xAA`` bytes at the
    start of sector 2 and metadata (cycle, file count, total sectors)
    that mirrors the first section. Those markers are distinctive
    enough — and corroborated by the cross-section sync — to rate
    STRONG, one rung above plain Acorn DFS, which is correct because
    the Acorn prober deliberately excludes discs carrying them.

    Reports the dfs family; like Acorn DFS the catalogue does not pin
    down sidedness or interleave, so the concrete geometry is left
    unresolved.
    """

    family = "dfs"
    extensions = frozenset({".ssd", ".dsd"})
    #: Outrank the Acorn prober when both somehow fire on one image —
    #: the extended catalogue is the more specific match.
    priority = 10

    def probe(self, reader: ImageReader) -> Iterable[Identification]:
        surface = _flat_surface(reader)
        if surface is None or not WatfordDFSCatalogue.matches(surface):
            return ()
        return (
            Identification(
                prober_name=self.name,
                family=self.family,
                confidence=Confidence.STRONG,
                evidence=(
                    "Watford DDFS extended catalogue: 0xAA marker in sector 2 "
                    "with metadata synced across both catalogue sections",
                ),
            ),
        )

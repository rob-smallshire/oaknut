"""The result model: confidence, partitions, and the identification tree.

:func:`~oaknut.filesystem.identify` returns a tree of
:class:`Identification` nodes — one per partition of an image, with
nested children for partitions reserved inside others (an ADFS host's
tail). Each node names the filesystem, a confidence and the evidence
for it, the proposed physical :class:`~oaknut.filesystem.Geometry`, and
any geometry the bytes cannot disambiguate.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace

from oaknut.filesystem.geometry import Geometry


class Confidence(enum.IntEnum):
    """How sure a filesystem is it identified a region — higher is surer.

    Candidates are ranked by this first, so an unambiguous magic number
    beats a structural heuristic, which beats a guess from size alone.
    """

    #: Only weak signals agree — image size, or nothing but the extension.
    POSSIBLE = 10
    #: Structural heuristics pass (e.g. a well-formed DFS catalogue).
    PROBABLE = 20
    #: Heuristics plus an integrity check agree (checksum, redundant copy).
    STRONG = 30
    #: An unambiguous on-disc magic number was found (e.g. ``AFS0``).
    CERTAIN = 40


@dataclass(frozen=True)
class Partition:
    """A named *logical sector* region within its parent.

    Sectors, not bytes, so a region of an interleaved host (an ADFS-L
    floppy's AFS tail) is contiguous: the bytes are scattered, but the
    logical sectors are a run. The coordinator materialises the bytes
    through the host's geometry (see :func:`region_reader`).

    *name* is the user-facing selector label — the filesystem the region
    is identified as (``"adfs"``, ``"afs"``) — and *index* disambiguates
    several partitions of the same kind (``afs.0``, ``afs.1``).
    """

    name: str
    start_sector: int
    num_sectors: int
    index: int = 0

    @property
    def selector(self) -> str:
        """The path selector for this partition (``afs`` or ``afs.1``)."""
        return self.name if self.index == 0 else f"{self.name}.{self.index}"


@dataclass(frozen=True)
class Identification:
    """What a filesystem reports a region to be.

    An empty :attr:`filesystem` marks a region that *something reserved*
    but no installed filesystem recognised — so a host disc with an
    unhandled tail still shows the tail honestly.
    """

    #: Filesystem extension key (``"acorn-dfs"``), or ``""`` if unidentified.
    filesystem: str
    #: How sure the identification is.
    confidence: Confidence
    #: Human-readable reasons it matched.
    evidence: tuple[str, ...] = ()
    #: The proposed physical geometry, when determinable.
    geometry: Geometry | None = None
    #: Equally-plausible geometries the content cannot distinguish.
    ambiguities: tuple[Geometry, ...] = ()
    #: The region this identifies (``None`` for the whole image / root).
    partition: Partition | None = None
    #: Regions reserved within this one, for the coordinator to recurse into.
    reserved_regions: tuple[Partition, ...] = ()
    #: Identifications of those reserved regions (filled by the coordinator).
    contained: tuple["Identification", ...] = field(default_factory=tuple)

    @property
    def identified(self) -> bool:
        """True unless this is a reserved-but-unrecognised region."""
        return bool(self.filesystem)

    def with_contained(self, contained: tuple["Identification", ...]) -> "Identification":
        """A copy with :attr:`contained` set (this dataclass is frozen)."""
        return replace(self, contained=contained)

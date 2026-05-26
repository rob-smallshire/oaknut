"""Content-based prober for AFS, plugged into oaknut.identify.

Registered under the ``oaknut.prober`` entry-point namespace (see this
package's ``pyproject.toml``), so the detector ships with the format it
detects and joins the identification cascade automatically.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.afs.exceptions import AFSInfoSectorError
from oaknut.afs.info_sector import INFO_SECTOR_SIZE, MAGIC, InfoSector
from oaknut.identify import Confidence, Identification, ImageReader, Prober


class AFSProber(Prober):
    """AFS — the Acorn Level 3 File Server's private on-disc format.

    An AFS region carries the ``AFS0`` magic at the start of its info
    sector, with a second identical copy one cylinder further on for
    redundancy. The region sits in the tail cylinders of an ADFS hard
    disc, so this prober scans sector-aligned offsets for the magic
    (skipping coincidental occurrences inside file data, which are not
    sector-aligned) and parses each candidate with the real info-sector
    decoder.

    Finding a well-formed info sector whose redundant copy matches is
    unambiguous — CERTAIN. A lone, unverified copy still rates STRONG.
    """

    family = "afs"
    extensions = frozenset({".dat"})

    def probe(self, reader: ImageReader) -> Iterable[Identification]:
        offset = reader.find(MAGIC, 0)
        while offset != -1:
            if offset % INFO_SECTOR_SIZE == 0:
                identification = self._identify_at(reader, offset)
                if identification is not None:
                    return (identification,)
            offset = reader.find(MAGIC, offset + 1)
        return ()

    def _identify_at(self, reader: ImageReader, offset: int) -> Identification | None:
        sector = reader.read(offset, INFO_SECTOR_SIZE)
        try:
            info = InfoSector.from_bytes(sector)
        except (AFSInfoSectorError, ValueError):
            # AFS0 at a sector boundary but not a well-formed info
            # sector — almost certainly a false positive, not AFS.
            return None

        verified = False
        if info.sectors_per_cylinder > 0:
            redundant_offset = offset + info.sectors_per_cylinder * INFO_SECTOR_SIZE
            redundant = reader.read(redundant_offset, INFO_SECTOR_SIZE)
            verified = redundant == sector

        evidence = [f"AFS0 info sector at byte {offset} (disc {info.disc_name!r})"]
        evidence.append(
            "redundant copy verified" if verified else "single info-sector copy found"
        )
        return Identification(
            prober_name=self.name,
            family=self.family,
            confidence=Confidence.CERTAIN if verified else Confidence.STRONG,
            evidence=tuple(evidence),
        )

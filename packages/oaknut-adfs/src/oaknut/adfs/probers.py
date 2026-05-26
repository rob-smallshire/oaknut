"""Content-based prober for ADFS, plugged into oaknut.identify.

Registered under the ``oaknut.prober`` entry-point namespace (see this
package's ``pyproject.toml``), so the detector ships with the format it
detects and joins the identification cascade automatically.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.adfs.free_space_map import _calculate_old_map_checksum
from oaknut.identify import Confidence, Identification, ImageReader, Prober

#: The old free-space map occupies sectors 0–1 (512 bytes); both must
#: be present to validate its checksums.
_MAP_BYTES = 512

#: Floppy image sizes that pin down the ADFS format.
_FLOPPY_SIZE_CLASSES = {
    163840: "ADFS S (40-track, single-sided)",
    327680: "ADFS M (80-track, single-sided)",
    655360: "ADFS L (80-track, double-sided)",
}


class ADFSProber(Prober):
    """ADFS — Acorn's hierarchical filing system (floppies and hard discs).

    Recognises the old-map layout used by S/M/L floppies and ST506
    hard discs through two independent signals: the root-directory
    signature (``Hugo`` for the old directory format at offset 0x201,
    ``Nick`` for the new directory format at 0x401) and the old
    free-space map's self-checksums in sectors 0–1. Either alone rates
    PROBABLE; together they rate STRONG.

    An AFS region, when present, lives in the tail cylinders of an ADFS
    hard disc and is reported separately by the AFS prober — this
    prober identifies only the ADFS host.
    """

    family = "adfs"
    extensions = frozenset({".adf", ".ads", ".adm", ".adl", ".dat"})

    def probe(self, reader: ImageReader) -> Iterable[Identification]:
        free_space_map = reader.read(0, _MAP_BYTES)
        if len(free_space_map) < _MAP_BYTES:
            return ()

        # The root-directory signature is the gating signal. The old-map
        # checksum alone is too weak to assert on — an all-zero block
        # trivially satisfies it (sum of zeros == the stored zero) — so
        # it only corroborates a directory we have already found.
        has_hugo = reader.read(0x201, 4) == b"Hugo"
        has_nick = reader.read(0x401, 4) == b"Nick"
        if not (has_hugo or has_nick):
            return ()

        map_valid = (
            _calculate_old_map_checksum(free_space_map, 0) == free_space_map[0xFF]
            and _calculate_old_map_checksum(free_space_map, 0x100) == free_space_map[0x1FF]
        )

        evidence: list[str] = []
        if has_hugo:
            evidence.append("old-format root directory signature ('Hugo')")
        else:
            evidence.append("new-format root directory signature ('Nick')")
        if map_valid:
            evidence.append("old-map free-space-map checksums valid (sectors 0–1)")
        size_label = _FLOPPY_SIZE_CLASSES.get(reader.size)
        if size_label is not None:
            evidence.append(f"image size matches {size_label}")

        confidence = Confidence.STRONG if map_valid else Confidence.PROBABLE
        return (
            Identification(
                prober_name=self.name,
                family=self.family,
                confidence=confidence,
                evidence=tuple(evidence),
            ),
        )

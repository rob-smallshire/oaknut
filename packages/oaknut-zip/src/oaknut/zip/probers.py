"""Content-based prober for ZIP archives, plugged into oaknut.identify.

Registered under the ``oaknut.prober`` entry-point namespace (see this
package's ``pyproject.toml``), so the detector ships with the format it
detects and joins the identification cascade automatically.
"""

from __future__ import annotations

from collections.abc import Iterable

from oaknut.identify import Confidence, Identification, ImageReader, Prober

#: ZIP records begin with a four-byte ``PK`` signature.
_SIGNATURES = {
    b"PK\x03\x04": "local file header",
    b"PK\x05\x06": "empty archive",
    b"PK\x07\x08": "spanned archive",
}


class ZipProber(Prober):
    """ZIP — archives that may carry Acorn files (SparkFS extras, RISC OS types).

    A ZIP file opens with an unambiguous ``PK`` signature, so detection
    is CERTAIN. This identifies the container only; whether it actually
    holds Acorn files is a separate question answered when the archive
    is opened.
    """

    family = "zip"
    extensions = frozenset({".zip"})

    def probe(self, reader: ImageReader) -> Iterable[Identification]:
        signature = reader.read(0, 4)
        kind = _SIGNATURES.get(signature)
        if kind is None:
            return ()
        return (
            Identification(
                prober_name=self.name,
                family=self.family,
                confidence=Confidence.CERTAIN,
                evidence=(f"ZIP signature ({kind}) at offset 0",),
            ),
        )

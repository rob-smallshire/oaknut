"""HFE on the ``oaknut.decoder`` axis.

Registering :class:`HFEDecoder` means every ``disc`` command that reads an
image (``ls``, ``cat``, ``get``, ``export``, ``identify``, …) opens an HFE
file as the sector image it flattens to, with no HFE-specific code in the
filesystems or the CLI.
"""

from __future__ import annotations

from oaknut.filesystem.decoder import DecodedImage, ImageDecoder
from oaknut.hfe.container import HFE_V1_SIGNATURE, HFE_V3_SIGNATURE, HFEImage
from oaknut.hfe.decode import decode_image
from oaknut.hfe.exceptions import HFEError
from oaknut.hfe.flat import FlatImage, flatten

__all__ = ["HFEDecoder", "flat_image_notes"]


class HFEDecoder(ImageDecoder):
    """HFE (HxC Floppy Emulator) flux images, v1 and v3, read-only.

    FM and MFM tracks are decoded to sectors and flattened into the
    disc's standard sector layout; unreadable sectors read as zeros.
    """

    extensions = frozenset({".hfe"})

    def recognises(self, prefix: bytes) -> bool:
        return prefix[:8] in (HFE_V1_SIGNATURE, HFE_V3_SIGNATURE)

    def decode(self, data: bytes) -> DecodedImage:
        image = HFEImage.from_bytes(data)
        flat = flatten(decode_image(image))
        if flat.layout is None:
            raise HFEError("no readable sectors in this HFE image")
        return DecodedImage(
            data=flat.data,
            suffix=flat.suffix,
            format_name=f"HFE v{image.header.version}",
            notes=flat_image_notes(flat),
        )


def flat_image_notes(flat: FlatImage) -> tuple[str, ...]:
    """User-facing remarks on how *flat* was made."""
    notes = []
    layout = flat.layout
    if layout is not None:
        notes.append(
            f"{layout.encoding.value}, {layout.num_tracks} tracks, {layout.num_sides} side(s), "
            f"{layout.sectors_per_track} x {layout.sector_size} bytes"
        )
        if layout.double_stepped:
            notes.append("double-stepped capture: every other physical track used")
    if flat.missing:
        notes.append(f"{len(flat.missing)} sector(s) unreadable, filled with zeros")
    return tuple(notes)

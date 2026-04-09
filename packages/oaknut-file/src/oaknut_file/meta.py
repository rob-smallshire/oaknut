"""Acorn file metadata representation.

The ``AcornMeta`` dataclass holds load/exec addresses, access
attributes, and filetype — the core metadata common to all Acorn
filing systems.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AcornMeta:
    """Acorn file metadata.

    Attributes:
        load_addr: 32-bit load address, or None if unknown.
        exec_addr: 32-bit execution address, or None if unknown.
        attr: Attribute byte (OSFILE convention), or None if unknown.
        filetype: RISC OS filetype (0x000–0xFFF), or None if unknown.
    """

    load_addr: int | None = None
    exec_addr: int | None = None
    attr: int | None = None
    filetype: int | None = None

    @property
    def has_metadata(self) -> bool:
        """True if any metadata is present."""
        return self.load_addr is not None

    @property
    def is_filetype_stamped(self) -> bool:
        """True if the load address encodes a RISC OS filetype.

        When the top 12 bits of the load address are 0xFFF, bits
        8–19 encode a filetype and bits 0–7 encode a date component.
        """
        if self.load_addr is None:
            return False
        return (self.load_addr & 0xFFF00000) == 0xFFF00000

    def infer_filetype(self) -> int | None:
        """Extract filetype from load address, or fall back to the filetype field."""
        if self.is_filetype_stamped:
            return (self.load_addr >> 8) & 0xFFF
        return self.filetype

"""Acorn file metadata representation.

The ``AcornMeta`` dataclass holds load/exec addresses, access
attributes, and filetype — the core metadata common to all Acorn
filing systems.
"""

from __future__ import annotations

import warnings


class AcornMeta:
    """Acorn file metadata.

    Attributes:
        load_address: 32-bit load address, or None if unknown.
        exec_address: 32-bit execution address, or None if unknown.
        access: Access byte (OSFILE convention), or None if unknown.
        filetype: RISC OS filetype (0x000–0xFFF), or None if unknown.

    Backwards-compatible constructor aliases ``load_addr``, ``exec_addr``,
    and ``attr`` are accepted but emit :class:`DeprecationWarning`. Use the
    explicit names in new code.
    """

    __slots__ = ("load_address", "exec_address", "access", "filetype")

    def __init__(
        self,
        load_address: int | None = None,
        exec_address: int | None = None,
        access: int | None = None,
        filetype: int | None = None,
        *,
        load_addr: int | None = None,
        exec_addr: int | None = None,
        attr: int | None = None,
    ) -> None:
        if load_addr is not None:
            warnings.warn(
                "AcornMeta(load_addr=) is deprecated; use load_address=",
                DeprecationWarning,
                stacklevel=2,
            )
            if load_address is None:
                load_address = load_addr
        if exec_addr is not None:
            warnings.warn(
                "AcornMeta(exec_addr=) is deprecated; use exec_address=",
                DeprecationWarning,
                stacklevel=2,
            )
            if exec_address is None:
                exec_address = exec_addr
        if attr is not None:
            warnings.warn(
                "AcornMeta(attr=) is deprecated; use access=",
                DeprecationWarning,
                stacklevel=2,
            )
            if access is None:
                access = attr
        self.load_address = load_address
        self.exec_address = exec_address
        self.access = access
        self.filetype = filetype

    def __repr__(self) -> str:
        return (
            f"AcornMeta(load_address={self.load_address!r}, "
            f"exec_address={self.exec_address!r}, "
            f"access={self.access!r}, "
            f"filetype={self.filetype!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AcornMeta):
            return NotImplemented
        return (
            self.load_address == other.load_address
            and self.exec_address == other.exec_address
            and self.access == other.access
            and self.filetype == other.filetype
        )

    def __hash__(self) -> int:
        return hash(
            (self.load_address, self.exec_address, self.access, self.filetype)
        )

    @property
    def has_metadata(self) -> bool:
        """True if any metadata is present."""
        return self.load_address is not None

    @property
    def is_filetype_stamped(self) -> bool:
        """True if the load address encodes a RISC OS filetype.

        When the top 12 bits of the load address are 0xFFF, bits
        8–19 encode a filetype and bits 0–7 encode a date component.
        """
        if self.load_address is None:
            return False
        return (self.load_address & 0xFFF00000) == 0xFFF00000

    def infer_filetype(self) -> int | None:
        """Extract filetype from load address, or fall back to the filetype field."""
        if self.is_filetype_stamped:
            return (self.load_address >> 8) & 0xFFF
        return self.filetype


# ----------------------------------------------------------------------
# Deprecated read/write aliases, exposed as descriptors so __slots__
# doesn't accidentally shadow them. Kept for one release.
# ----------------------------------------------------------------------


def _alias(new_name: str, old_name: str):
    def fget(self: AcornMeta):
        warnings.warn(
            f"AcornMeta.{old_name} is deprecated; use {new_name}",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self, new_name)

    def fset(self: AcornMeta, value):
        warnings.warn(
            f"AcornMeta.{old_name} is deprecated; use {new_name}",
            DeprecationWarning,
            stacklevel=2,
        )
        setattr(self, new_name, value)

    return property(fget, fset)


# __slots__ blocks attribute creation but does not block class-level
# property descriptors named differently from the slot names.
AcornMeta.load_addr = _alias("load_address", "load_addr")  # type: ignore[attr-defined]
AcornMeta.exec_addr = _alias("exec_address", "exec_addr")  # type: ignore[attr-defined]
AcornMeta.attr = _alias("access", "attr")  # type: ignore[attr-defined]

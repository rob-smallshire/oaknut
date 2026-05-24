"""Parser for Acorn load / execution addresses.

Addresses are written as Python-style integer literals: the base is
taken from the prefix — ``0x``/``0X`` hex, ``0o`` octal, ``0b``
binary — or decimal when there is no prefix. The Acorn ``&`` hex
sigil is deliberately not accepted; callers write ``0x`` instead, so
one base-spelling convention covers every numeric argument in the
CLI.
"""

from __future__ import annotations

from oaknut.file.exceptions import InvalidAddressError


def parse_address(text: str) -> int:
    """Parse a load/exec address literal, honouring its base prefix.

    ``0x1900`` is hex, ``0o14400`` octal, ``0b1`` binary, and a bare
    ``6400`` decimal. Raises :class:`InvalidAddressError` if *text* is
    not a valid integer literal.
    """
    try:
        return int(text, 0)
    except ValueError:
        raise InvalidAddressError(
            f"invalid address {text!r}: prefix hex with 0x (e.g. 0x1900), "
            "or give a plain decimal value"
        ) from None

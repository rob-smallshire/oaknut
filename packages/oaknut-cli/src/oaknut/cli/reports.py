"""Report-rendering helpers shared across ``disc`` commands.

Audience-aware cells (a friendly string for humans, a raw value for
machine formatters) and a transposed key-value table, used by both the
generic ``disc`` commands and the filesystem-contributed ones. Built on
asyoulikeit; kept here, below the filesystem packages, so a contributed
command can render output without depending on ``oaknut-disc``.
"""

from __future__ import annotations

from asyoulikeit import ByAudience
from oaknut.file.capacity import format_capacity

#: Acorn discs are addressed in 256-byte sectors throughout.
SECTOR_SIZE = 256

# The Unicode Control Pictures block (U+2400–U+241F) holds a visible,
# inert glyph for each C0 control character (0x00–0x1F); U+2421 (␡) is
# the symbol for DEL (0x7F). Mapping to these never emits an active
# control code, so a terminal is never driven by data read off a disc.
_CONTROL_PICTURES = {codepoint: chr(0x2400 + codepoint) for codepoint in range(0x20)}
_CONTROL_PICTURES[0x7F] = "␡"
_CONTROL_PICTURES_TABLE = str.maketrans(_CONTROL_PICTURES)


def control_pictures(text: str) -> str:
    """Render C0 control characters and DEL as Unicode Control Pictures.

    Acorn names and titles are stored as arbitrary bytes and may carry
    control characters (a disc title decorated with a form-feed, say).
    This replaces each with the matching glyph from the Control Pictures
    block so it is visible and inert; all other characters pass through.
    """
    return text.translate(_CONTROL_PICTURES_TABLE)


def text_cell(text: str) -> str | ByAudience:
    """On-disc text that may contain control characters, as a cell.

    Clean text is returned unchanged, so the common case is untouched.
    When control characters are present the cell becomes audience-aware:
    machine formatters (JSON, TSV) keep the raw string for a faithful
    round-trip, while the display formatter shows :func:`control_pictures`
    so the terminal is never driven by active control codes.
    """
    pretty = control_pictures(text)
    if pretty == text:
        return text
    return ByAudience(machine=text, human=pretty)


def size_cell(sectors: int) -> ByAudience:
    """A capacity (given in sectors) as an audience-aware cell.

    Humans read friendly IEC units (``800.0 KiB``); machine formatters
    get the raw byte count as an integer, so the presentation base is
    irrelevant to a consumer.
    """
    num_bytes = sectors * SECTOR_SIZE
    return ByAudience(machine=num_bytes, human=format_capacity(num_bytes))


def bytes_cell(num_bytes: int) -> ByAudience:
    """A byte count as an audience-aware cell.

    Like :func:`size_cell`, but for a value already in bytes (a file
    length) rather than sectors: humans read friendly IEC units
    (``9.9 KiB``); machine formatters get the raw integer.
    """
    return ByAudience(machine=num_bytes, human=format_capacity(num_bytes))


def address_cell(address: int) -> ByAudience:
    """An Acorn load/exec address as an audience-aware cell.

    Humans read the ``0x``-prefixed hex form, trimmed of leading zeros
    to a whole number of bytes (an even count of hex digits) with a
    minimum of six — the width Acorn MOS uses for a DFS address, so a
    table stays narrow without diverging from ``*EX`` / ``*INFO``. A
    larger address (an ADFS 32-bit value) grows in whole bytes. Machine
    formatters (JSON, TSV) get the raw integer, so a consumer never has
    to parse a base back out of a string.
    """
    digits = max(6, len(f"{address:X}"))
    width = digits + (digits & 1)  # round up to a whole number of bytes
    return ByAudience(machine=address, human=f"0x{address:0{width}X}")


def kv_table(title: str, pairs: list[tuple[str, str, object]]):
    """Build a transposed single-row table from (key, label, value) tuples.

    Each tuple becomes a column whose sole row holds the value. A value
    may be a plain string, an integer (for machine-readable counts), or
    a :class:`~asyoulikeit.ByAudience` cell that renders one way for
    humans and another for machine formatters. Transposed presentation
    turns the one-row table into a key-value report in the display
    formatter.
    """
    from asyoulikeit.tabular_data import TableContent

    tc = TableContent(title=title, present_transposed=True)
    row: dict = {}
    for index, (key, label, value) in enumerate(pairs):
        tc.add_column(key, label, header=(index == 0))
        row[key] = value
    tc.add_row(**row)
    return tc

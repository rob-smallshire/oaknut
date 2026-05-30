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
    """A 32-bit Acorn address as an audience-aware cell.

    Humans read the conventional ``0x``-prefixed 8-hex-digit form;
    machine formatters (JSON, TSV) get the raw integer, so a consumer
    never has to parse a base back out of a string.
    """
    return ByAudience(machine=address, human=f"0x{address:08X}")


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

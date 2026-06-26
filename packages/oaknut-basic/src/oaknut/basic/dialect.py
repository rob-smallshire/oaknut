"""BBC BASIC dialects for de-tokenisation.

The :mod:`~oaknut.basic.tokens` table is **BBC BASIC II** — the BBC
Micro's 8-bit language ROM. BBC BASIC V (the Archimedes / RISC OS ARM
BASIC) keeps that table but extends it two ways, and de-tokenising a
BASIC V program with the BASIC II table corrupts every extended keyword:

- Three BASIC II command tokens — ``&C6``, ``&C7``, ``&C8`` (``AUTO``,
  ``DELETE``, ``LOAD``) — become **two-byte escape prefixes**. The byte
  that follows selects an extended keyword, with the second byte counting
  from ``&8E`` in each table: ``&C6`` for the extended *functions*
  (``SUM``, ``BEAT``), ``&C7`` for the extended *commands* (``APPEND`` …
  ``RENUMBER`` … ``INSTALL``), and ``&C8`` for the extended *statements*
  (``CASE``, ``CIRCLE``, ``ORIGIN``, ``SYS`` …).

- Several single-byte slots are re-purposed. ``&7F`` becomes
  ``OTHERWISE``, and ``&C9``-``&CE`` — ``LIST``/``NEW``/``OLD``/
  ``RENUMBER``/``SAVE`` and an unused gap in BASIC II — become the block
  keywords ``WHEN``/``OF``/``ENDCASE``/``ELSE``/``ENDIF``/``ENDWHILE``
  (the command spellings move into the ``&C7`` escape table).

A :class:`Dialect` bundles the single-byte token map with the escape
tables, so the scanner and de-tokeniser can target either language with
one parameter. :data:`BASIC_II` is the default everywhere — code that
does not name a dialect keeps its existing BASIC II behaviour.

The token values were cross-checked against two independent
implementations: Justin Fletcher's de-tokeniser tables (the
``gerph/riscos-basic-detokenise`` ``c/basic`` source) and Steve Fryatt's
``tokenize`` (``src/parse.c``), which agree byte-for-byte.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from oaknut.basic.tokens import TOKEN_TO_KEYWORD


@dataclass(frozen=True)
class Dialect:
    """A BBC BASIC variant's token-to-keyword mapping.

    Attributes:
        name: Human-readable dialect name (e.g. ``"BBC BASIC V"``).
        single_byte: Maps a single token byte to its keyword spelling.
            Covers the whole one-byte keyword range, including the few
            sub-``&80`` tokens such as ``&7F`` (``OTHERWISE``).
        escape: Maps a two-byte escape *prefix* (``&C6``/``&C7``/``&C8``
            in BASIC V) to a table from the *following* byte to its
            extended keyword. Empty for dialects without escape tokens.
    """

    name: str
    single_byte: Mapping[int, str]
    escape: Mapping[int, Mapping[int, str]]


# --- BBC BASIC II -----------------------------------------------------------

#: BBC BASIC II — the BBC Micro's 8-bit language ROM. No escape tokens;
#: the single-byte map is the canonical :data:`TOKEN_TO_KEYWORD` table.
BASIC_II = Dialect(name="BBC BASIC II", single_byte=TOKEN_TO_KEYWORD, escape=MappingProxyType({}))


# --- BBC BASIC V ------------------------------------------------------------

# The extended-token tables, keyed by the byte that follows the prefix.
# Each runs from &8E upward, in ROM order.
_EXTENDED_FUNCTIONS = ("SUM", "BEAT")
_EXTENDED_COMMANDS = (
    "APPEND",
    "AUTO",
    "CRUNCH",
    "DELETE",
    "EDIT",
    "HELP",
    "LIST",
    "LOAD",
    "LVAR",
    "NEW",
    "OLD",
    "RENUMBER",
    "SAVE",
    "TEXTLOAD",
    "TEXTSAVE",
    "TWIN",
    "TWINO",
    "INSTALL",
)
_EXTENDED_STATEMENTS = (
    "CASE",
    "CIRCLE",
    "FILL",
    "ORIGIN",
    "POINT",
    "RECTANGLE",
    "SWAP",
    "WHILE",
    "WAIT",
    "MOUSE",
    "QUIT",
    "SYS",
    "INSTALL",
    "LIBRARY",
    "TINT",
    "ELLIPSE",
    "BEATS",
    "TEMPO",
    "VOICES",
    "VOICE",
    "STEREO",
    "OVERLAY",
)

_EXTENDED_TOKEN_BASE = 0x8E


def _extended_table(keywords: tuple[str, ...]) -> Mapping[int, str]:
    """Build a {second byte -> keyword} table counting from ``&8E``."""
    return MappingProxyType(
        {_EXTENDED_TOKEN_BASE + offset: keyword for offset, keyword in enumerate(keywords)}
    )


# Single-byte tokens BASIC V re-purposes from BASIC II. &7F is new;
# &C9-&CE displace the LIST/NEW/OLD/RENUMBER/SAVE command tokens (whose
# spellings move into the &C7 escape table) and the unused &CE gap.
_BASIC_V_SINGLE_BYTE_OVERRIDES = {
    0x7F: "OTHERWISE",
    0xC9: "WHEN",
    0xCA: "OF",
    0xCB: "ENDCASE",
    0xCC: "ELSE",
    0xCD: "ENDIF",
    0xCE: "ENDWHILE",
}

# Start from BASIC II, drop the three bytes that are now escape prefixes
# (so a bare prefix never resolves to AUTO/DELETE/LOAD), then apply the
# re-purposed single-byte slots.
_basic_v_single_byte = {
    token: keyword
    for token, keyword in TOKEN_TO_KEYWORD.items()
    if token not in (0xC6, 0xC7, 0xC8)
}
_basic_v_single_byte.update(_BASIC_V_SINGLE_BYTE_OVERRIDES)

#: BBC BASIC V — the Archimedes / RISC OS ARM BASIC. Adds the
#: ``&C6``/``&C7``/``&C8`` escape tables and the re-purposed single-byte
#: tokens described in this module's docstring.
BASIC_V = Dialect(
    name="BBC BASIC V",
    single_byte=MappingProxyType(_basic_v_single_byte),
    escape=MappingProxyType(
        {
            0xC6: _extended_table(_EXTENDED_FUNCTIONS),
            0xC7: _extended_table(_EXTENDED_COMMANDS),
            0xC8: _extended_table(_EXTENDED_STATEMENTS),
        }
    ),
)

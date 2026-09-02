"""The greedy crunch mode (``tokenise(..., crunch="greedy")``).

The BBC BASIC ROM's crunch is only one of the tokenisers that produced
tokenised BBC BASIC in the wild. A class of early-1980s commercial
programs was crunched by a *greedier* tool whose keyword recognition
differs from the ROM in three specific ways, so their de-tokenised source
does not re-tokenise byte-identically under the ROM-accurate default.

``crunch="greedy"`` reproduces that tool. The default (``crunch="rom"``)
stays byte-exact to the ROM, so the two modes are pinned side by side on
the same source below.

The three rule differences (see :func:`oaknut.basic.tokenise`):

- **Rule 1** — a keyword interrupts a hex constant. The ROM copies every
  ``0``-``9`` / ``A``-``F`` in a ``&`` run unconditionally; greedy stops
  the run where a keyword begins (``&FE60ANDROW%`` -> ``&FE60``, ``AND``,
  ``ROW%``).
- **Rule 2** — an ``FN``/``PROC`` name terminates at a ``FLAG_START``
  keyword (``THEN``/``ELSE``). The ROM's name-skip swallows every
  alphanumeric; greedy keeps the first name character but breaks the name
  at a following ``THEN``/``ELSE`` — and *only* those, so a function
  keyword embedded in a name (``READ`` in ``PROCREADKP``) is left intact.
- **Rule 3** — refined conditional suppression. The ROM keeps a
  conditional keyword literal whenever a name character follows; greedy
  does so only when that character does not itself begin a keyword, so
  ``STOP`` before ``ELSE`` tokenises while ``NEW`` in ``NEWKEY%`` stays
  literal.

The two commercial programs under ``data/greedy`` (Voltmace / Custom
Video Productions, 1983) validate the whole model: their own
``detokenise`` output re-tokenises byte-for-byte under greedy.
"""

from pathlib import Path

import pytest
from oaknut.basic import detokenise, tokenise

_DATA_DIRPATH = Path(__file__).parent / "data"
_GREEDY_DIRPATH = _DATA_DIRPATH / "greedy"


def _body(statement: str, *, crunch: str = "rom") -> bytes:
    """Tokenise a single body (no leading space) and return its bytes."""
    program = tokenise("10" + statement, crunch=crunch)
    length = program[3]
    return program[4:length]


# (source after the line number, ROM body, greedy body). The ROM column is
# the current default and must not change; the greedy column reproduces the
# commercial files. Values transcribed from issue #48.
_VECTORS = [
    # Rule 1 — a keyword interrupts a hex constant.
    (
        "A=?&FE60ANDROW%",
        bytes.fromhex("41 3d 3f 26 46 45 36 30 41 4e 44 52 4f 57 25"),
        bytes.fromhex("41 3d 3f 26 46 45 36 30 80 52 4f 57 25"),
    ),
    # Rule 2 — an FN/PROC name breaks at a FLAG_START keyword (THEN/ELSE).
    (
        "IFA THENPROCWTKEYELSEPROCBKKEY",
        bytes.fromhex(
            "e7 41 20 8c f2 57 54 4b 45 59 45 4c 53 45 50 52 4f 43 42 4b 4b 45 59"
        ),
        bytes.fromhex("e7 41 20 8c f2 57 54 4b 45 59 8b f2 42 4b 4b 45 59"),
    ),
    # Rule 2 — a function keyword embedded in a name is not a break point.
    (
        "PROCREADKP",
        bytes.fromhex("f2 52 45 41 44 4b 50"),
        bytes.fromhex("f2 52 45 41 44 4b 50"),
    ),
    # Rule 3 — a conditional keyword before another keyword tokenises.
    (
        "IFA=1THENSTOPELSEGOTO90",
        bytes.fromhex("e7 41 3d 31 8c 53 54 4f 50 45 4c 53 45 47 4f 54 4f 39 30"),
        bytes.fromhex("e7 41 3d 31 8c fa 8b e5 8d 44 5a 40"),
    ),
    # Rule 3 — a conditional keyword before a plain name char stays literal.
    (
        "NEWKEY%=0",
        bytes.fromhex("4e 45 57 4b 45 59 25 3d 30"),
        bytes.fromhex("4e 45 57 4b 45 59 25 3d 30"),
    ),
]


@pytest.mark.parametrize(
    ("source", "rom_body", "greedy_body"),
    _VECTORS,
    ids=[v[0] for v in _VECTORS],
)
def test_rom_default_is_unchanged(source, rom_body, greedy_body):
    assert _body(source, crunch="rom") == rom_body


@pytest.mark.parametrize(
    ("source", "rom_body", "greedy_body"),
    _VECTORS,
    ids=[v[0] for v in _VECTORS],
)
def test_greedy_reproduces_the_greedier_tool(source, rom_body, greedy_body):
    assert _body(source, crunch="greedy") == greedy_body


def test_default_crunch_is_rom():
    # The default must remain ROM-accurate: an un-flagged call matches "rom".
    source = "10 A=?&FE60ANDROW%"
    assert tokenise(source) == tokenise(source, crunch="rom")


def _program_lines(program: bytes) -> dict[int, bytes]:
    """Split a stored program into ``{line_number: body_bytes}``."""
    lines: dict[int, bytes] = {}
    offset = 0
    while offset + 3 < len(program):
        if program[offset] != 0x0D or program[offset + 1] == 0xFF:
            break
        record_length = program[offset + 3]
        number = (program[offset + 1] << 8) | program[offset + 2]
        lines[number] = program[offset + 4 : offset + record_length]
        offset += record_length
    return lines


class TestCommercialPrograms:
    """The KEYPAD / JOYSTIK Voltmace programs round-trip under greedy."""

    def test_keypad_round_trips_byte_identically(self):
        program = (_GREEDY_DIRPATH / "keypad.tokens").read_bytes()
        assert tokenise(detokenise(program), crunch="greedy") == program

    def test_joystik_round_trips_except_the_encryption_boundary_line(self):
        # JOYSTIK's line 1890 is the file's ROL-encryption boundary line, a
        # decode artefact of that binary rather than a tokeniser difference;
        # every other line re-tokenises byte-for-byte under greedy.
        program = (_GREEDY_DIRPATH / "joystik.tokens").read_bytes()
        retokenised = tokenise(detokenise(program), crunch="greedy")
        original = _program_lines(program)
        rebuilt = _program_lines(retokenised)
        differing = [n for n in original if original[n] != rebuilt.get(n)]
        assert differing == [1890]

    def test_rom_crunch_does_not_round_trip_the_greedy_files(self):
        # Guard the premise: the ROM-accurate default cannot regenerate a
        # program the greedier tool produced.
        program = (_GREEDY_DIRPATH / "keypad.tokens").read_bytes()
        assert tokenise(detokenise(program), crunch="rom") != program

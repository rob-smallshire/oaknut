"""The ROM filing-system service handler, for created ROMs.

A serialised ROMFS is inert on a real machine without a service handler:
the OS reads the filing system only through paged-ROM service calls ``&0D``
(initialise — point the read pointer at the data) and ``&0E`` (return the
next byte). See ``docs/romfs-format-spec.md`` §2.10.

This module assembles that handler. The 6502 is the canonical handler from
the *New Advanced User Guide* (as used by ``mkromfs``'s ``handlesvc.asm``):
it answers ``&0D`` / ``&0E`` for its own ROM and passes every other call
on. The ``&0D`` path follows the genuine Acornsoft ROMs rather than mkromfs
in two ways the *New Advanced User Guide* example gets wrong: it treats a
negative serial-ROM scan number as "initialise from the top" (so a created
ROM works on the Electron, whose MOS issues the init with ``Y`` negative),
and it guards the scan number against wrapping past the sixteen sockets (so
a ROM in socket 0 does not loop ``*CAT``). See :data:`_CORE_BODY`. A small
two-pass assembler resolves the branch and jump targets so the machine code
is correct by construction rather than hand-counted.

The handler is hand-assembled and verified for layout and length here;
its execution is confirmed in a 6502 emulator (a created ROM answers
``*HELP``, ``*CAT``, ``CHAIN`` and ``*TYPE`` correctly).
"""

from __future__ import annotations

#: Zero-page locations the OS uses for the ROM filing system.
_ROM_ID = 0xF4  # the ROM's own socket number
_SER_ROM = 0xF5  # the current filing-system ROM (15 - socket)
_ROM_PTR = 0xF6  # the read pointer (two bytes, &F6/&F7)
_OSRDRM = 0xFFB9  # OS routine: read a byte from a paged ROM
_OSASCI = 0xFFE3  # OS routine: write a character (CR also emits LF)
_OSNEWL = 0xFFE7  # OS routine: write a newline (CR + LF)
_TITLE_ADDRESS = 0x8009  # the paged-ROM header title is always here

#: Opcode and total length for each (mnemonic, addressing mode) used here.
_OPCODES: dict[tuple[str, str], tuple[int, int]] = {
    ("CMP", "imm"): (0xC9, 2),
    ("CMP", "zp"): (0xC5, 2),
    ("LDA", "imm"): (0xA9, 2),
    ("LDA", "zp"): (0xA5, 2),
    ("LDA", "zpy"): (0xB1, 2),  # LDA (zp),Y
    ("LDA", "absx"): (0xBD, 3),  # LDA addr,X
    ("STA", "zp"): (0x85, 2),
    ("LDY", "imm"): (0xA0, 2),
    ("LDX", "imm"): (0xA2, 2),
    ("EOR", "imm"): (0x49, 2),
    ("AND", "imm"): (0x29, 2),
    ("INC", "zp"): (0xE6, 2),
    ("INX", "imp"): (0xE8, 1),
    ("BEQ", "rel"): (0xF0, 2),
    ("BNE", "rel"): (0xD0, 2),
    ("BCC", "rel"): (0x90, 2),
    ("BCS", "rel"): (0xB0, 2),
    ("BMI", "rel"): (0x30, 2),
    ("JMP", "abs"): (0x4C, 3),
    ("JSR", "abs"): (0x20, 3),
    ("PHA", "imp"): (0x48, 1),
    ("PLA", "imp"): (0x68, 1),
    ("TAY", "imp"): (0xA8, 1),
    ("TYA", "imp"): (0x98, 1),
    ("TAX", "imp"): (0xAA, 1),
    ("TXA", "imp"): (0x8A, 1),
    ("RTS", "imp"): (0x60, 1),
}

# The handler, as (label, mnemonic, mode, operand). An ``imm`` operand may be
# an int or ("lo"|"hi", symbol) for the low/high byte of an address; ``abs``
# and ``rel`` operands are label names (internal labels, or the externals
# "data", "OSRDRM", "OSWRCH"); ``zp``/``zpy`` operands are zero-page
# addresses; ``absx`` an absolute address.

# Service-call dispatch. With the *HELP handler, &09 is tested first and the
# "service" entry label sits on it; otherwise it sits on the &0D test.
_HELP_DISPATCH = [
    ("service", "CMP", "imm", 0x09),  # *HELP?
    (None, "BEQ", "rel", "dohelp"),
    (None, "CMP", "imm", 0x0D),  # initialise filing system?
    (None, "BEQ", "rel", "initsp"),
    (None, "CMP", "imm", 0x0E),  # read byte?
    (None, "BEQ", "rel", "rdbyte"),
    (None, "RTS", "imp", None),  # not ours
]
_PLAIN_DISPATCH = [
    ("service", "CMP", "imm", 0x0D),  # initialise filing system?
    (None, "BEQ", "rel", "initsp"),
    (None, "CMP", "imm", 0x0E),  # read byte?
    (None, "BEQ", "rel", "rdbyte"),
    (None, "RTS", "imp", None),  # not ours
]

# The &0D / &0E core (the mkromfs / NAUG handler body), shared by both.
# The &0D path follows the genuine Acornsoft ROMs rather than mkromfs, in two
# ways the example handler in the New Advanced User Guide gets wrong:
#   * Negative scan number -> "select self". The OS passes the serial-ROM scan
#     number in Y. The BBC seeds it &FF and INCs to &00 (positive); the
#     Electron seeds it &EF and INCs to &F0, so its init call arrives with Y
#     negative. A negative Y means "initialise from the top RFS ROM", so claim
#     unconditionally — without this an oaknut ROM never initialises on an Elk.
#   * Wrap guard. After each &2B the OS INCs the scan number to hunt a
#     continuation ROM in a lower socket. mkromfs masks it with AND #&0F, so
#     when it wraps &0F->&10 a socket-0 ROM folds back to 15 and re-claims
#     itself, looping *CAT forever. Inverting with EOR #&0F (high nibble
#     intact) and testing CMP #&10 lets the hunt terminate.
_CORE_BODY = [
    ("initsp", "PHA", "imp", None),
    (None, "TYA", "imp", None),  # A = the serial-ROM scan number (Y)
    (None, "BMI", "rel", "selfsel"),  # negative (Electron init) -> select self
    (None, "EOR", "imm", 0x0F),  # invert; high nibble kept for the wrap test
    (None, "CMP", "imm", 0x10),  # scan advanced past the sixteen sockets?
    (None, "BCS", "rel", "exit"),  # yes — exhausted, don't re-claim (socket-0 loop)
    (None, "CMP", "zp", _ROM_ID),
    (None, "BCC", "rel", "exit"),  # scanned ROM below us — not yet our turn
    ("selfsel", "LDA", "imm", ("lo", "data")),
    (None, "STA", "zp", _ROM_PTR),
    (None, "LDA", "imm", ("hi", "data")),
    (None, "STA", "zp", _ROM_PTR + 1),
    (None, "LDA", "zp", _ROM_ID),
    (None, "JSR", "abs", "invert"),
    (None, "STA", "zp", _SER_ROM),  # make us the current filing-system ROM
    ("claim", "PLA", "imp", None),
    (None, "LDA", "imm", 0x00),  # claim the call
    (None, "RTS", "imp", None),
    ("exit", "PLA", "imp", None),
    (None, "RTS", "imp", None),
    ("rdbyte", "PHA", "imp", None),
    (None, "TYA", "imp", None),
    (None, "BMI", "rel", "os120"),  # Y negative: OS has OSRDRM
    (None, "JSR", "abs", "invsno"),
    (None, "CMP", "zp", _ROM_ID),
    (None, "BNE", "rel", "exit"),  # not our ROM
    (None, "LDY", "imm", 0x00),
    (None, "LDA", "zpy", _ROM_PTR),  # A = byte at (pointer)
    (None, "TAY", "imp", None),
    ("claim1", "INC", "zp", _ROM_PTR),
    (None, "BNE", "rel", "claim"),
    (None, "INC", "zp", _ROM_PTR + 1),
    (None, "JMP", "abs", "claim"),
    ("os120", "JSR", "abs", "invsno"),
    (None, "TAY", "imp", None),
    (None, "JSR", "abs", "OSRDRM"),  # OS selects the ROM and reads the byte
    (None, "TAY", "imp", None),
    (None, "JMP", "abs", "claim1"),
    ("invsno", "LDA", "zp", _SER_ROM),
    ("invert", "EOR", "imm", 0xFF),
    (None, "AND", "imm", 0x0F),
    (None, "RTS", "imp", None),
]

# The optional *HELP (&09) routine, after Bruce Smith's *Advanced Sideways
# RAM User Guide* §4: print a blank line, the ROM's header title (always at
# &8009), and a blank line, for the conventional *HELP layout. Unlike that
# book's minimal example it preserves A/X/Y and returns with A unchanged
# (= 9), so the call is *not* claimed and the MOS keeps polling lower ROMs —
# the sidewrom notes' "restore A and Y and pass on" rule. The title is the
# user-set message.
_HELP_ROUTINE = [
    ("dohelp", "PHA", "imp", None),  # save A (= 9)
    (None, "TXA", "imp", None),
    (None, "PHA", "imp", None),  # save X
    (None, "TYA", "imp", None),
    (None, "PHA", "imp", None),  # save Y
    (None, "JSR", "abs", "OSNEWL"),  # blank line before
    (None, "LDX", "imm", 0x00),
    ("helploop", "LDA", "absx", _TITLE_ADDRESS),  # next title character
    (None, "BEQ", "rel", "helpdone"),  # NUL terminator
    (None, "JSR", "abs", "OSASCI"),
    (None, "INX", "imp", None),
    (None, "BNE", "rel", "helploop"),  # always (title < 256 bytes)
    ("helpdone", "JSR", "abs", "OSNEWL"),  # blank line after
    (None, "PLA", "imp", None),  # restore Y
    (None, "TAY", "imp", None),
    (None, "PLA", "imp", None),  # restore X
    (None, "TAX", "imp", None),
    (None, "PLA", "imp", None),  # restore A (= 9)
    (None, "RTS", "imp", None),  # pass on (do not claim &09)
]


def _program(with_help: bool) -> list:
    """The full instruction list for the chosen handler variant."""
    if with_help:
        return _HELP_DISPATCH + _CORE_BODY + _HELP_ROUTINE
    return _PLAIN_DISPATCH + _CORE_BODY


def _layout(program: list) -> tuple[dict[str, int], int]:
    """First pass: assign an offset to each label and return the total length."""
    labels: dict[str, int] = {}
    offset = 0
    for label, mnemonic, mode, _operand in program:
        if label is not None:
            labels[label] = offset
        offset += _OPCODES[(mnemonic, mode)][1]
    return labels, offset


#: Length of the bare &0D/&0E handler (87 bytes: the mkromfs body plus the
#: negative-Y "select self" and scan-number wrap handling in the &0D path).
HANDLER_LENGTH = _layout(_program(with_help=False))[1]


def rfs_handler_length(*, with_help: bool = False) -> int:
    """The assembled length of the chosen handler variant, in bytes."""
    return _layout(_program(with_help))[1]


def build_rfs_handler(base_address: int, data_address: int, *, with_help: bool = False) -> bytes:
    """Assemble the service handler placed at *base_address*.

    *data_address* is the absolute address of the filing-system data the
    handler points the OS at on initialisation. With *with_help*, a ``&09``
    ``*HELP`` responder is included that prints the ROM's title.
    """
    program = _program(with_help)
    labels, _length = _layout(program)
    externals = {
        "data": data_address,
        "OSRDRM": _OSRDRM,
        "OSASCI": _OSASCI,
        "OSNEWL": _OSNEWL,
    }

    def address_of(symbol: str) -> int:
        if symbol in externals:
            return externals[symbol]
        return base_address + labels[symbol]

    out = bytearray()
    offset = 0
    for _label, mnemonic, mode, operand in program:
        opcode, length = _OPCODES[(mnemonic, mode)]
        out.append(opcode)
        if mode == "imp":
            pass
        elif mode == "imm":
            if isinstance(operand, tuple):
                half, symbol = operand
                value = address_of(symbol)
                out.append(value & 0xFF if half == "lo" else (value >> 8) & 0xFF)
            else:
                out.append(operand & 0xFF)
        elif mode in ("zp", "zpy"):
            out.append(operand & 0xFF)
        elif mode == "absx":
            out.append(operand & 0xFF)
            out.append((operand >> 8) & 0xFF)
        elif mode == "rel":
            target = labels[operand]
            displacement = target - (offset + length)
            if not -128 <= displacement <= 127:
                raise ValueError(f"branch to {operand} out of range: {displacement}")
            out.append(displacement & 0xFF)
        elif mode == "abs":
            address = address_of(operand)
            out.append(address & 0xFF)
            out.append((address >> 8) & 0xFF)
        offset += length
    return bytes(out)

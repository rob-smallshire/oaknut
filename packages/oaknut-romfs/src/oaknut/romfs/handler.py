"""The ROM filing-system service handler, for created ROMs.

A serialised ROMFS is inert on a real machine without a service handler:
the OS reads the filing system only through paged-ROM service calls ``&0D``
(initialise — point the read pointer at the data) and ``&0E`` (return the
next byte). See ``docs/romfs-format-spec.md`` §2.10.

This module assembles that handler. The 6502 is the canonical handler from
the *New Advanced User Guide* (as used by ``mkromfs``'s ``handlesvc.asm``):
it answers ``&0D`` / ``&0E`` for its own ROM and passes every other call
on. A small two-pass assembler resolves the branch and jump targets so the
machine code is correct by construction rather than hand-counted; the
result is exactly 81 bytes, matching mkromfs (which places the filing-system
data at ``&805D`` for an empty header).

The handler is hand-assembled and verified for layout and length here;
execution on real hardware is to be confirmed against a 6502 emulator.
"""

from __future__ import annotations

#: Zero-page locations the OS uses for the ROM filing system.
_ROM_ID = 0xF4  # the ROM's own socket number
_SER_ROM = 0xF5  # the current filing-system ROM (15 - socket)
_ROM_PTR = 0xF6  # the read pointer (two bytes, &F6/&F7)
_OSRDRM = 0xFFB9  # OS routine: read a byte from a paged ROM

#: Opcode and total length for each (mnemonic, addressing mode) used here.
_OPCODES: dict[tuple[str, str], tuple[int, int]] = {
    ("CMP", "imm"): (0xC9, 2),
    ("CMP", "zp"): (0xC5, 2),
    ("LDA", "imm"): (0xA9, 2),
    ("LDA", "zp"): (0xA5, 2),
    ("LDA", "zpy"): (0xB1, 2),  # LDA (zp),Y
    ("STA", "zp"): (0x85, 2),
    ("LDY", "imm"): (0xA0, 2),
    ("EOR", "imm"): (0x49, 2),
    ("AND", "imm"): (0x29, 2),
    ("INC", "zp"): (0xE6, 2),
    ("BEQ", "rel"): (0xF0, 2),
    ("BNE", "rel"): (0xD0, 2),
    ("BCC", "rel"): (0x90, 2),
    ("BMI", "rel"): (0x30, 2),
    ("JMP", "abs"): (0x4C, 3),
    ("JSR", "abs"): (0x20, 3),
    ("PHA", "imp"): (0x48, 1),
    ("PLA", "imp"): (0x68, 1),
    ("TAY", "imp"): (0xA8, 1),
    ("TYA", "imp"): (0x98, 1),
    ("RTS", "imp"): (0x60, 1),
}

# The handler, as (label, mnemonic, mode, operand). An ``imm`` operand may be
# an int or ("lo"|"hi", symbol) for the low/high byte of an address; ``abs``
# and ``rel`` operands are label names (internal labels, or the externals
# "data" and "OSRDRM"); ``zp``/``zpy`` operands are zero-page addresses.
_PROGRAM = [
    ("service", "CMP", "imm", 0x0D),  # initialise filing system?
    (None, "BEQ", "rel", "initsp"),
    (None, "CMP", "imm", 0x0E),  # read byte?
    (None, "BEQ", "rel", "rdbyte"),
    (None, "RTS", "imp", None),  # not ours
    ("initsp", "PHA", "imp", None),
    (None, "JSR", "abs", "invsno"),  # A = inverted *ROM number
    (None, "CMP", "zp", _ROM_ID),
    (None, "BCC", "rel", "exit"),  # scanned ROM below us — not yet our turn
    (None, "LDA", "imm", ("lo", "data")),
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


def _layout() -> tuple[dict[str, int], int]:
    """First pass: assign an offset to each label and return the total length."""
    labels: dict[str, int] = {}
    offset = 0
    for label, mnemonic, mode, _operand in _PROGRAM:
        if label is not None:
            labels[label] = offset
        offset += _OPCODES[(mnemonic, mode)][1]
    return labels, offset


_LABELS, HANDLER_LENGTH = _layout()


def build_rfs_handler(base_address: int, data_address: int) -> bytes:
    """Assemble the service handler placed at *base_address*.

    *data_address* is the absolute address of the filing-system data the
    handler points the OS at on initialisation. Returns exactly
    :data:`HANDLER_LENGTH` bytes.
    """
    externals = {"data": data_address, "OSRDRM": _OSRDRM}

    def address_of(symbol: str) -> int:
        if symbol in externals:
            return externals[symbol]
        return base_address + _LABELS[symbol]

    out = bytearray()
    offset = 0
    for _label, mnemonic, mode, operand in _PROGRAM:
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
        elif mode == "rel":
            target = _LABELS[operand]
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

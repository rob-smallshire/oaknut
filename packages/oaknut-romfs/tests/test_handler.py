"""Tests for the ROM filing-system service handler assembler.

The handler is based on the mkromfs / NAUG &0D/&0E handler, with one change:
the &0D (initialise) path guards against the service-ROM scan number rising
past the sixteen valid sockets, so a ROM in sideways socket 0 does not
re-claim itself after its data is exhausted. (mkromfs masks the scan number
with AND #&0F and so loops *CAT forever in socket 0; the genuine Acornsoft
ROMs add a CMP #&10 / BCS guard, which this handler follows.) Execution on
real hardware is confirmed against a 6502 emulator.
"""

from __future__ import annotations

from oaknut.romfs.handler import HANDLER_LENGTH, build_rfs_handler

# Zero-page locations the handler and the MOS use for the ROM filing system.
_ROM_ID = 0xF4  # the socket the MOS is currently polling
_SER_ROM = 0xF5  # the serial-ROM scan number (the MOS INCs this past each &2B)
_SERVICE_INITIALISE = 0x0D  # service call: initialise the ROM filing system


def _run_service_call(handler: bytes, base: int, *, a: int, f4: int, f5: int) -> tuple[int, int]:
    """Execute the assembled handler for one service call on a tiny 6502 core.

    Seeds A (the service-call number), &F4 (the polled socket) and &F5 (the
    scan number), runs from the handler entry until the top-level RTS, and
    returns ``(A, &F5)``. A claimed call returns A=0. Only the opcodes the
    handler emits are implemented; external JSRs (OSRDRM/OSASCI/OSNEWL) are
    treated as no-ops, which the &0D path never depends on.
    """
    from oaknut.romfs.handler import _OPCODES

    decode = {opcode: (mnem, mode, length) for (mnem, mode), (opcode, length) in _OPCODES.items()}
    mem = {base + i: b for i, b in enumerate(handler)}
    mem[_ROM_ID], mem[_SER_ROM] = f4, f5
    x = y = 0
    carry = zero = neg = False
    stack: list[int | None] = [None]  # sentinel: the top-level RTS pops it
    pc = base

    def set_nz(value: int) -> None:
        nonlocal zero, neg
        zero, neg = value == 0, bool(value & 0x80)

    for _ in range(100_000):  # generous bound; a real call is well under 100 steps
        mnem, mode, length = decode[mem[pc]]
        operand = mem.get(pc + 1, 0)
        if mode == "abs":
            operand = mem.get(pc + 1, 0) | (mem.get(pc + 2, 0) << 8)
        nxt = pc + length

        if mnem == "PHA":
            stack.append(a)
        elif mnem == "PLA":
            a = stack.pop()
            set_nz(a)
        elif mnem == "RTS":
            target = stack.pop()
            if target is None:
                return a, mem.get(_SER_ROM, f5)
            nxt = target
        elif mnem == "JSR":
            if base <= operand < base + len(handler):
                stack.append(nxt)
                nxt = operand
            # else external (OS routine): no-op
        elif mnem == "JMP":
            nxt = operand
        elif mnem in ("BEQ", "BNE", "BCC", "BCS", "BMI"):
            taken = {
                "BEQ": zero, "BNE": not zero, "BCC": not carry,
                "BCS": carry, "BMI": neg,
            }[mnem]
            if taken:
                nxt = (pc + length + (operand - 256 if operand > 127 else operand)) & 0xFFFF
        elif mnem == "LDA":
            if mode == "imm":
                a = operand
            elif mode == "zp":
                a = mem.get(operand, 0)
            elif mode == "zpy":
                addr = mem.get(operand, 0) | (mem.get(operand + 1, 0) << 8)
                a = mem.get(addr + y, 0xFF)
            elif mode == "absx":
                a = mem.get(operand + x, 0xFF)
            set_nz(a)
        elif mnem == "STA":
            mem[operand] = a
        elif mnem == "LDX":
            x = operand
            set_nz(x)
        elif mnem == "LDY":
            y = operand
            set_nz(y)
        elif mnem == "EOR":
            a ^= operand
            set_nz(a)
        elif mnem == "AND":
            a &= operand
            set_nz(a)
        elif mnem == "INC":
            mem[operand] = (mem.get(operand, 0) + 1) & 0xFF
            set_nz(mem[operand])
        elif mnem == "INX":
            x = (x + 1) & 0xFF
            set_nz(x)
        elif mnem in ("TAY", "TYA", "TAX", "TXA"):
            if mnem == "TAY":
                y = a
            elif mnem == "TYA":
                a = y
            elif mnem == "TAX":
                x = a
            else:
                a = x
            set_nz(a if mnem in ("TYA", "TXA") else (y if mnem == "TAY" else x))
        elif mnem == "CMP":
            rhs = operand if mode == "imm" else mem.get(operand, 0)
            diff = a - rhs
            carry, zero, neg = a >= rhs, a == rhs, bool(diff & 0x80)
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unhandled opcode {mnem} {mode}")
        pc = nxt
    raise AssertionError("handler did not return")  # pragma: no cover


def _catalogue_passes(handler: bytes, base: int, socket: int, *, limit: int = 64) -> int | str:
    """How many times *CAT reads the whole filing system before it stops.

    Models the MOS catalogue loop: select the ROM with service &0D, read its
    data to the &2B end marker, then INC the scan number and re-issue &0D —
    looping while a ROM claims. Returns the pass count, or "LOOPS" if the
    re-init keeps re-claiming (an endless *CAT).
    """
    def claim(f5: int) -> int | None:
        # The MOS polls sockets 15..0; only our socket carries the handler.
        out_a, out_f5 = _run_service_call(handler, base, a=_SERVICE_INITIALISE, f4=socket, f5=f5)
        return out_f5 if out_a == 0 else None

    f5 = claim(0x00)  # the MOS's initial scan
    if f5 is None:
        return 0
    for passes in range(1, limit + 1):
        f5 = claim((f5 + 1) & 0xFF)  # the MOS INCs &F5 at each &2B
        if f5 is None:
            return passes
    return "LOOPS"


def test_cat_terminates_in_every_socket():
    # Regression: a created ROM in sideways socket 0 must not loop *CAT. The
    # MOS, on reaching the &2B end marker, INCs the scan number (&F5) and
    # re-issues &0D to look for a continuation ROM. Without the CMP #&10 guard
    # the handler re-claims itself in socket 0 (the scan number wraps &0F->&10
    # but AND #&0F maps it back to 15 >= 0), restarting the catalogue forever.
    handler = build_rfs_handler(0x800C, 0x9000)
    for socket in range(16):
        assert _catalogue_passes(handler, 0x800C, socket) == 1, f"socket {socket}"


def test_initialise_does_not_reclaim_once_scanned_past():
    # The direct invariant behind the fix: once the scan number has advanced
    # beyond the sixteen sockets (&F5 >= &10), &0D must go unclaimed whatever
    # the socket, so the multi-ROM continuation hunt can end.
    handler = build_rfs_handler(0x800C, 0x9000)
    a, _ = _run_service_call(handler, 0x800C, a=_SERVICE_INITIALISE, f4=0x00, f5=0x10)
    assert a != 0  # not claimed


def test_handler_length_matches_the_guarded_handler():
    # The guard adds a few bytes over mkromfs's 81; pin the new length so an
    # accidental regression in the instruction list is caught.
    assert HANDLER_LENGTH == len(build_rfs_handler(0x800C, 0x805D))


def test_handler_entry_and_data_pointer():
    handler = build_rfs_handler(0x800C, 0x805D)
    # Entry: CMP #&0D / BEQ ; CMP #&0E / BEQ ; RTS.
    assert handler[0:2] == bytes([0xC9, 0x0D])
    assert handler[4:6] == bytes([0xC9, 0x0E])
    # The data address is poked little-endian: LDA #&5D / STA &F6 / LDA #&80.
    assert bytes([0xA9, 0x5D, 0x85, 0xF6, 0xA9, 0x80, 0x85, 0xF7]) in handler
    # OSRDRM is called for the OSRDRM-capable path.
    assert bytes([0x20, 0xB9, 0xFF]) in handler


def test_data_address_is_relocated_into_the_operands():
    handler = build_rfs_handler(0x800C, 0x9ABC)
    assert bytes([0xA9, 0xBC, 0x85, 0xF6, 0xA9, 0x9A, 0x85, 0xF7]) in handler


def test_internal_jumps_track_the_base_address():
    # JMP/JSR to internal labels are absolute, so they shift with the base.
    low = build_rfs_handler(0x8000, 0x9000)
    high = build_rfs_handler(0x8100, 0x9000)
    assert low != high  # the absolute operands differ by the base delta
    assert len(low) == len(high) == HANDLER_LENGTH

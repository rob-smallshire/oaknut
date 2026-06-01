"""Well-known Econet port numbers and immediate-operation control codes.

The values are taken from the Acorn NFS/ANFS disassembly (the client side of
the file-server, print, and immediate protocols) and the Acorn Econet Bridge
disassembly (the bridge protocol port). They are consistent across the eleven
disassembled NFS/ANFS versions.
"""

from __future__ import annotations

from enum import IntEnum


class Port(IntEnum):
    """Well-known Econet port numbers.

    Ports are an 8-bit demultiplexing key chosen by the receiver; these are the
    conventional assignments. Port 0 carries immediate operations rather than
    normal data. (Note: NFS/ANFS uses &D1 for the print server data port; some
    implementations also use &9F for the print-server query.)
    """

    #: Immediate operations (PEEK, POKE, ..., MachinePeek) — serviced by the NMI.
    IMMEDIATE = 0x00
    #: File-server reply port (PREPLY).
    FS_REPLY = 0x90
    #: File-server save/acknowledge and data-block port.
    FS_SAVE_ACK = 0x91
    #: File-server load data port (PLDATA).
    FS_LOAD_DATA = 0x92
    #: Remote operations port.
    REMOTE = 0x93
    #: File-server command port (PFSCMD) — *I AM, directory ops, etc.
    FS_COMMAND = 0x99
    #: Bridge protocol port (WhatNet/IsNet/Reset/Update) — from the Acorn bridge.
    BRIDGE = 0x9C
    #: Print-server port (NFS/ANFS port_printer).
    PRINTER = 0xD1


class ImmediateOp(IntEnum):
    """Immediate-operation control bytes carried on :attr:`Port.IMMEDIATE`.

    These run in the receiver's NMI handler without application involvement.
    From the NFS/ANFS immediate-op dispatch table (control bytes &81–&88).
    """

    #: Read memory from the remote station.
    PEEK = 0x81
    #: Write memory to the remote station.
    POKE = 0x82
    #: Call a subroutine on the remote station.
    JSR = 0x83
    #: User procedure call.
    USER_PROCEDURE = 0x84
    #: OS procedure call.
    OS_PROCEDURE = 0x85
    #: Halt the remote station.
    HALT = 0x86
    #: Resume a halted remote station.
    CONTINUE = 0x87
    #: Query the remote station's machine type (MachinePeek).
    MACHINE_PEEK = 0x88

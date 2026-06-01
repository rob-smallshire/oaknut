"""Contract for the well-known port numbers and immediate-operation codes."""

from oaknut.econet.core import ImmediateOp, Port


def test_well_known_ports():
    assert Port.IMMEDIATE == 0x00
    assert Port.FS_REPLY == 0x90
    assert Port.FS_SAVE_ACK == 0x91
    assert Port.FS_LOAD_DATA == 0x92
    assert Port.REMOTE == 0x93
    assert Port.FS_COMMAND == 0x99
    assert Port.BRIDGE == 0x9C
    assert Port.PRINTER == 0xD1


def test_ports_behave_as_ints():
    assert isinstance(Port.FS_COMMAND, int)
    assert Port.FS_COMMAND + 0 == 0x99


def test_immediate_operation_codes():
    assert ImmediateOp.PEEK == 0x81
    assert ImmediateOp.POKE == 0x82
    assert ImmediateOp.JSR == 0x83
    assert ImmediateOp.USER_PROCEDURE == 0x84
    assert ImmediateOp.OS_PROCEDURE == 0x85
    assert ImmediateOp.HALT == 0x86
    assert ImmediateOp.CONTINUE == 0x87
    assert ImmediateOp.MACHINE_PEEK == 0x88


def test_immediate_operations_span_0x81_to_0x88():
    assert sorted(int(op) for op in ImmediateOp) == list(range(0x81, 0x89))

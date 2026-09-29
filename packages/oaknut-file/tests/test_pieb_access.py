"""PiEconetBridge ``perm`` is its own layout, not the Acorn access byte (#70).

PiEconetBridge ``utilities/fs.c``::

    #define FS_PERM_H 0x80     // Hidden
    #define FS_PERM_OTH_W 0x20 // Write by others
    #define FS_PERM_OTH_R 0x10 // Read by others
    #define FS_PERM_EXEC 0x08  // Execute only
    #define FS_PERM_L 0x04     // Locked
    #define FS_PERM_OWN_W 0x02 // Write by owner
    #define FS_PERM_OWN_R 0x01 // Read by owner

The lock and execute bits are swapped relative to the OSFILE byte.
"""

from __future__ import annotations

import pytest
from oaknut.file import PIEB_ACCESS, Access, AccessConvention, PiEconetBridgeAccessConvention
from oaknut.file.inf import format_pieb_inf_line, parse_inf_line


def test_is_an_access_convention():
    assert isinstance(PIEB_ACCESS, PiEconetBridgeAccessConvention)
    assert isinstance(PIEB_ACCESS, AccessConvention)
    assert PIEB_ACCESS.name == "pieb"


@pytest.mark.parametrize(
    ("perm", "canonical"),
    [
        (0x03, Access(0x03)),  # WR/
        (0x13, Access(0x13)),  # WR/R
        (0x33, Access(0x33)),  # WR/WR
        (0x04, Access.L),  # locked: PiEB 0x04 is L, not E
        (0x05, Access.L | Access.R),  # LR/
        (0x17, Access(0x1B)),  # LWR/R — what oaknut used to write as its "default"
        (0x08, Access.E),  # execute only: run-only
        (0x80 | 0x13, Access(0x13)),  # hidden has no canonical bit
    ],
)
def test_to_canonical(perm, canonical):
    assert PIEB_ACCESS.to_canonical(perm) == canonical


@pytest.mark.parametrize(
    ("canonical", "perm"),
    [
        (Access(0x03), 0x03),
        (Access(0x13), 0x13),
        (Access.L | Access.R, 0x05),
        (Access(0x1B), 0x17),
        (Access.E, 0x08),  # run-only becomes PiEB execute-only
        (Access.E | Access.R, 0x01),  # E alongside R is not run-only
    ],
)
def test_from_canonical(canonical, perm):
    assert PIEB_ACCESS.from_canonical(canonical) == perm


def test_from_canonical_keeps_the_hidden_bit_of_the_current_perm():
    assert PIEB_ACCESS.from_canonical(Access(0x13), current=0x80) == 0x93


def test_run_only_is_run_only_after_reading():
    assert PIEB_ACCESS.to_canonical(0x08).is_run_only


def test_pieb_inf_line_is_read_through_the_convention():
    _source, meta = parse_inf_line("0 1900 8023 04")
    assert meta.access == int(Access.L)


def test_pieb_inf_line_is_written_through_the_convention():
    assert format_pieb_inf_line(0x1900, 0x8023, attr=int(Access.L | Access.R)).endswith(" 5")


def test_pieb_inf_default_is_wr_r():
    # PiEB's own default for a new file is WR/R (0x13), not oaknut's old 0x17.
    assert format_pieb_inf_line(0x1900, 0x8023).endswith(" 13")


def test_a_locked_file_survives_a_pieb_inf_round_trip():
    line = format_pieb_inf_line(0x1900, 0x8023, attr=int(Access.L | Access.R | Access.PR))
    _source, meta = parse_inf_line(line)
    assert meta.access == int(Access.L | Access.R | Access.PR)

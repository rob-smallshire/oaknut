"""Tests for the ADFS access convention."""

from __future__ import annotations

from dataclasses import replace

import pytest
from oaknut.adfs import ADFS_ACCESS, ADFSAccessConvention
from oaknut.adfs.directory import _ADFSRawAttributes
from oaknut.file import DIRECTORY_CONTEXT, Access, AccessConvention

_PLAIN = _ADFSRawAttributes(
    owner_read=False,
    owner_write=False,
    locked=False,
    directory=False,
    owner_execute=False,
    public_read=False,
    public_write=False,
    public_execute=False,
    private=False,
)


def test_is_an_access_convention():
    assert isinstance(ADFS_ACCESS, ADFSAccessConvention)
    assert isinstance(ADFS_ACCESS, AccessConvention)
    assert ADFS_ACCESS.name == "adfs"


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, Access(0)),
        ({"owner_read": True, "owner_write": True}, Access(0x03)),
        ({"owner_read": True, "owner_write": True, "public_read": True}, Access(0x13)),
        ({"owner_read": True, "locked": True, "public_read": True}, Access(0x19)),
        ({"owner_execute": True}, Access.E),
        ({"public_write": True}, Access.PW),
        ({"public_execute": True}, Access.PE),
        # The private bit is bit 7 (BeebWiki: "cannot be deleted ... by public").
        ({"private": True}, Access.PL),
        ({"directory": True}, Access(0)),
    ],
)
def test_to_canonical(flags, expected):
    assert ADFS_ACCESS.to_canonical(replace(_PLAIN, **flags)) == expected


def test_from_canonical_sets_the_eight_bits():
    raw = ADFS_ACCESS.from_canonical(Access(0xFF))
    assert (raw.owner_read, raw.owner_write, raw.owner_execute, raw.locked) == (True,) * 4
    assert (raw.public_read, raw.public_write, raw.public_execute) == (True,) * 3
    assert raw.private
    assert not raw.directory


def test_from_canonical_preserves_the_directory_bit():
    current = replace(_PLAIN, directory=True, public_execute=True, private=True, owner_read=True)
    raw = ADFS_ACCESS.from_canonical(Access.L, DIRECTORY_CONTEXT, current=current)
    assert raw.locked and not raw.owner_read
    assert raw.directory
    # Public execute and private are now in the word, so it decides them.
    assert not (raw.public_execute or raw.private)


def test_from_canonical_takes_directory_from_context_without_current():
    assert ADFS_ACCESS.from_canonical(Access.L, DIRECTORY_CONTEXT).directory
    assert not ADFS_ACCESS.from_canonical(Access.L).directory


def test_round_trip_for_every_representable_value():
    for value in range(0x100):
        access = Access(value)
        assert ADFS_ACCESS.settle(access) == access


# -- New and Big directories (#67) --

from oaknut.adfs import (  # noqa: E402
    ADFS,
    ADFS_D,
    ADFS_E_PLUS,
    ADFS_F,
    ADFS_L,
    ADFS_NEW_DIRECTORY_ACCESS,
    ADFS_S,
)


def test_new_directory_convention_cannot_hold_execute():
    assert ADFS_NEW_DIRECTORY_ACCESS.name == "adfs-new-directory"
    assert not ADFS_NEW_DIRECTORY_ACCESS.representable & Access.E
    assert ADFS_NEW_DIRECTORY_ACCESS.settle(Access(0x07)) == Access(0x03)
    assert ADFS_NEW_DIRECTORY_ACCESS.settle(Access(0x3B)) == Access(0x3B)
    assert ADFS_NEW_DIRECTORY_ACCESS.settle(Access.E) == Access(0)


def test_new_directory_convention_drops_what_the_byte_cannot_store():
    current = replace(_PLAIN, public_execute=True, private=True)
    raw = ADFS_NEW_DIRECTORY_ACCESS.from_canonical(Access(0x07), current=current)
    assert not (raw.owner_execute or raw.public_execute or raw.private)


@pytest.mark.parametrize(
    ("disc_format", "convention"),
    [
        (ADFS_S, ADFS_ACCESS),
        (ADFS_L, ADFS_ACCESS),
        (ADFS_D, ADFS_NEW_DIRECTORY_ACCESS),
        (ADFS_F, ADFS_NEW_DIRECTORY_ACCESS),
        (ADFS_E_PLUS, ADFS_NEW_DIRECTORY_ACCESS),
    ],
)
def test_disc_chooses_the_convention_for_its_directory_format(disc_format, convention):
    assert ADFS.create(disc_format).access_convention is convention


@pytest.mark.parametrize("disc_format", [ADFS_D, ADFS_F, ADFS_E_PLUS])
def test_what_settle_promises_is_what_a_new_format_disc_stores(disc_format):
    adfs = ADFS.create(disc_format)
    path = adfs.root / "F"
    path.write_bytes(b"x")
    for value in (0x07, 0x1B, 0x33, 0x04):
        path.chmod(value)
        assert path.stat().access == adfs.access_convention.settle(Access(value)), hex(value)


# -- write_bytes applies access through the convention (#63) --


@pytest.mark.parametrize("value", [0x19, 0x33, 0x0B, 0x07, 0x01])
def test_write_bytes_applies_the_whole_access(value):
    adfs = ADFS.create(ADFS_L)
    (adfs.root / "F").write_bytes(b"x", access=Access(value))
    assert (adfs.root / "F").stat().access == Access(value)


def test_write_bytes_on_a_new_format_disc_keeps_what_it_can():
    adfs = ADFS.create(ADFS_F)
    (adfs.root / "F").write_bytes(b"x", access=Access(0x07))
    assert (adfs.root / "F").stat().access == Access(0x03)


def test_write_bytes_without_access_gives_a_new_file_the_default():
    adfs = ADFS.create(ADFS_L)
    (adfs.root / "F").write_bytes(b"x")
    assert (adfs.root / "F").stat().access == Access(0x13)  # WR/R


def test_replacing_a_file_without_access_keeps_its_access():
    adfs = ADFS.create(ADFS_L)
    path = adfs.root / "F"
    path.write_bytes(b"one", access=Access(0x33))
    path.write_bytes(b"two")
    assert path.read_bytes() == b"two"
    assert path.stat().access == Access(0x33)


def test_replacing_a_file_with_access_sets_it():
    adfs = ADFS.create(ADFS_L)
    path = adfs.root / "F"
    path.write_bytes(b"one", access=Access(0x33))
    path.write_bytes(b"two", access=Access(0x03))
    assert path.stat().access == Access(0x03)


# -- Public execute and private through the disc (#60 step 4) --


def test_old_directory_disc_keeps_public_execute_and_private():
    adfs = ADFS.create(ADFS_L)
    path = adfs.root / "F"
    path.write_bytes(b"x", access=Access(0xD3))  # PE | PL | PR | W | R
    assert path.stat().access == Access(0xD3)


def test_chmod_sets_public_execute():
    adfs = ADFS.create(ADFS_S)
    path = adfs.root / "F"
    path.write_bytes(b"x")
    path.chmod(Access(0x43))
    assert path.stat().access == Access(0x43)


def test_new_directory_disc_cannot_store_them():
    assert ADFS_NEW_DIRECTORY_ACCESS.settle(Access(0xD3)) == Access(0x13)

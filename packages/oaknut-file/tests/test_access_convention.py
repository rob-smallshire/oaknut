"""Tests for the access-convention core: contexts, settling and translation."""

from __future__ import annotations

import pytest
from oaknut.file import (
    DIRECTORY_CONTEXT,
    FILE_CONTEXT,
    Access,
    AccessContext,
    AccessConvention,
    parse_access_spec,
    translate_access,
)


class LockOnly(AccessConvention[bool]):
    """A DFS-like toy: the native form is a lone locked flag."""

    name = "toy-lock-only"
    family = "toy"
    representable = Access.L | Access.R | Access.W
    source = "test double"

    def to_canonical(self, native: bool, context: AccessContext = FILE_CONTEXT) -> Access:
        return Access.R | Access.W | (Access.L if native else Access(0))

    def from_canonical(
        self, access: Access, context: AccessContext = FILE_CONTEXT, current: bool | None = None
    ) -> bool:
        return bool(access & Access.L)


class OwnerPublic(AccessConvention[int]):
    """A toy that stores owner and public R/W/L verbatim."""

    name = "toy-owner-public"
    family = "toy"
    representable = Access.R | Access.W | Access.L | Access.PR | Access.PW
    source = "test double"

    def to_canonical(self, native: int, context: AccessContext = FILE_CONTEXT) -> Access:
        return Access(native) & self.representable

    def from_canonical(
        self, access: Access, context: AccessContext = FILE_CONTEXT, current: int | None = None
    ) -> int:
        return int(access & self.representable)


class TestContext:
    def test_file_and_directory_contexts(self):
        assert FILE_CONTEXT == AccessContext()
        assert not FILE_CONTEXT.is_directory
        assert DIRECTORY_CONTEXT.is_directory
        assert DIRECTORY_CONTEXT.filetype is None

    def test_context_carries_a_filetype(self):
        assert AccessContext(filetype=0xFE6).filetype == 0xFE6


class TestSettle:
    def test_settle_is_what_the_convention_can_hold(self):
        # Only L survives the lock-only native form; R and W are its fixed base.
        assert LockOnly().settle(Access.L | Access.PR) == Access.L | Access.R | Access.W
        assert LockOnly().settle(Access.PR) == Access.R | Access.W

    def test_settle_is_idempotent(self):
        for value in range(0x80):
            once = OwnerPublic().settle(Access(value))
            assert OwnerPublic().settle(once) == once

    def test_convention_is_abstract(self):
        with pytest.raises(TypeError):
            AccessConvention()  # type: ignore[abstract]


class TestTranslateAccess:
    def test_default_is_what_the_destination_holds(self):
        assert translate_access(Access.L | Access.PR, destination=LockOnly()) == Access(0x0B)
        assert translate_access(Access(0x13), destination=OwnerPublic()) == Access(0x13)

    def test_grant_public_copies_owner_read_and_write(self):
        assert translate_access(Access.WR, destination=OwnerPublic(), grant_public=True) == Access(
            0x33
        )
        assert translate_access(
            Access.L | Access.R, destination=OwnerPublic(), grant_public=True
        ) == Access(0x19)

    def test_grant_public_is_off_by_default(self):
        assert translate_access(Access.WR, destination=OwnerPublic()) == Access.WR

    def test_override_applies_after_grant(self):
        remove_public_write = parse_access_spec("-/W")
        assert translate_access(
            Access.WR, destination=OwnerPublic(), grant_public=True, override=remove_public_write
        ) == Access(0x13)

    def test_absolute_override_replaces(self):
        assert translate_access(
            Access.LWR, destination=OwnerPublic(), override=parse_access_spec("R/R")
        ) == Access(0x11)

    def test_result_is_settled_by_the_destination(self):
        # An override granting public read is still limited by what the
        # destination can store.
        assert (
            translate_access(Access.WR, destination=LockOnly(), override=parse_access_spec("+/R"))
            == Access.WR
        )

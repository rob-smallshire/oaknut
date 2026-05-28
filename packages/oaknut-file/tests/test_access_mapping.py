"""Tests for cross-filesystem access attribute mapping."""

from oaknut.file.access import Access
from oaknut.file.access_mapping import access_from_stat


class FakeDFSStat:
    locked: bool = False


class FakeADFSStat:
    locked: bool = False
    owner_read: bool = True
    owner_write: bool = True
    owner_execute: bool = False
    public_read: bool = True
    public_write: bool = False
    public_execute: bool = False

    @property
    def access(self):
        return Access(
            (Access.R if self.owner_read else 0)
            | (Access.W if self.owner_write else 0)
            | (Access.E if self.owner_execute else 0)
            | (Access.L if self.locked else 0)
            | (Access.PR if self.public_read else 0)
            | (Access.PW if self.public_write else 0)
        )


class FakeAFSStat:
    """An AFS stat exposes a *canonical* wire Access — its on-disc byte is
    already translated (AFSAccess.to_acorn) — so this layer needs no AFS
    bit knowledge."""

    def __init__(self, access: Access):
        self.access = access
        self.load_address = 0
        self.exec_address = 0


class TestAccessFromStat:
    def test_dfs_unlocked(self):
        st = FakeDFSStat()
        st.locked = False
        result = access_from_stat(st)
        # DFS unlocked → default WR/
        assert result & Access.R
        assert result & Access.W
        assert not (result & Access.L)

    def test_dfs_locked(self):
        st = FakeDFSStat()
        st.locked = True
        result = access_from_stat(st)
        assert result & Access.L

    def test_adfs_full_access(self):
        st = FakeADFSStat()
        result = access_from_stat(st)
        assert result & Access.R
        assert result & Access.W
        assert result & Access.PR
        assert not (result & Access.L)

    def test_adfs_locked(self):
        st = FakeADFSStat()
        st.locked = True
        result = access_from_stat(st)
        assert result & Access.L

    def test_afs_stat(self):
        # An AFS stat hands back a canonical Access directly.
        st = FakeAFSStat(Access.R | Access.W | Access.PR)
        result = access_from_stat(st)
        assert result == Access.R | Access.W | Access.PR

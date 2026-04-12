"""Tests for cross-filesystem access attribute mapping."""

from oaknut.file.access import Access
from oaknut.file.access_mapping import access_from_stat, access_to_write_kwargs


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


class FakeAFSAccess:
    """Mimics AFSAccess with the bits we care about."""

    def __init__(self, *, owner_read=False, owner_write=False, locked=False,
                 public_read=False, public_write=False, is_directory=False):
        self._or = owner_read
        self._ow = owner_write
        self._l = locked
        self._pr = public_read
        self._pw = public_write
        self._d = is_directory

    @property
    def is_locked(self):
        return self._l

    @property
    def is_directory(self):
        return self._d

    def __and__(self, other):
        return int(self) & other

    def __int__(self):
        v = 0
        if self._pr:
            v |= 0x01
        if self._pw:
            v |= 0x02
        if self._or:
            v |= 0x04
        if self._ow:
            v |= 0x08
        if self._l:
            v |= 0x10
        if self._d:
            v |= 0x20
        return v


class FakeAFSStat:
    def __init__(self, access):
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
        afs_access = FakeAFSAccess(owner_read=True, owner_write=True, public_read=True)
        st = FakeAFSStat(afs_access)
        result = access_from_stat(st)
        assert result & Access.R
        assert result & Access.W
        assert result & Access.PR


class TestAccessToWriteKwargs:
    def test_for_dfs(self):
        access = Access.L | Access.W | Access.R
        kwargs = access_to_write_kwargs(access, "dfs")
        assert kwargs == {"locked": True}

    def test_for_dfs_unlocked(self):
        access = Access.W | Access.R
        kwargs = access_to_write_kwargs(access, "dfs")
        assert kwargs == {"locked": False}

    def test_for_adfs(self):
        access = Access.L | Access.W | Access.R
        kwargs = access_to_write_kwargs(access, "adfs")
        assert kwargs == {"locked": True}

    def test_for_afs(self):
        access = Access.L | Access.W | Access.R | Access.PR
        kwargs = access_to_write_kwargs(access, "afs")
        # Should produce an AFSAccess-compatible value.
        assert "access" in kwargs
        afs_val = kwargs["access"]
        assert afs_val & 0x10  # locked
        assert afs_val & 0x04  # owner read
        assert afs_val & 0x08  # owner write
        assert afs_val & 0x01  # public read

"""Tests for ADFSPath.chmod() and the Access IntFlag enum."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S
from oaknut_dfs.adfs_directory import Access
from oaknut_dfs.exceptions import ADFSPathError


class TestAccessEnum:

    def test_individual_flags(self):
        assert Access.R.value == 0x01
        assert Access.W.value == 0x02
        assert Access.E.value == 0x04
        assert Access.L.value == 0x08

    def test_combination(self):
        rw = Access.R | Access.W
        assert Access.R in rw
        assert Access.W in rw
        assert Access.L not in rw

    def test_repr(self):
        assert "R" in repr(Access.R)
        assert "W" in repr(Access.W)

    def test_empty(self):
        empty = Access(0)
        assert Access.R not in empty
        assert Access.W not in empty
        assert Access.L not in empty
        assert Access.E not in empty


class TestAccessOsfileCompatibility:
    """Verify bit values match the Acorn OSFILE API convention."""

    def test_owner_read_is_bit_0(self):
        assert Access.R == 0x01

    def test_owner_write_is_bit_1(self):
        assert Access.W == 0x02

    def test_execute_only_is_bit_2(self):
        assert Access.E == 0x04

    def test_locked_is_bit_3(self):
        assert Access.L == 0x08

    def test_public_read_is_bit_4(self):
        assert Access.PR == 0x10

    def test_public_write_is_bit_5(self):
        assert Access.PW == 0x20

    def test_wr_matches_pieb_default_owner_bits(self):
        """WR (0x03) matches the owner bits of PiEconetBridge's default perm."""
        assert int(Access.R | Access.W) == 0x03

    def test_pieb_default_perm(self):
        """PiEconetBridge default perm 0x17 = PR | E | W | R."""
        flags = Access(0x17)
        assert Access.R in flags
        assert Access.W in flags
        assert Access.E in flags
        assert Access.L not in flags
        assert Access.PR in flags
        assert Access.PW not in flags

    def test_integer_round_trip(self):
        """Access flags can be constructed from an integer attribute byte."""
        attr_byte = 0x0B  # R | W | L
        flags = Access(attr_byte)
        assert Access.R in flags
        assert Access.W in flags
        assert Access.L in flags
        assert Access.E not in flags

    def test_full_byte_round_trip(self):
        """Full attribute byte with public bits."""
        attr_byte = 0x33  # R | W | PR | PW
        flags = Access(attr_byte)
        assert Access.R in flags
        assert Access.W in flags
        assert Access.PR in flags
        assert Access.PW in flags
        assert Access.L not in flags
        assert int(flags) == 0x33


class TestChmod:

    def test_chmod_lock(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access.R | Access.W | Access.L)
        stat = (adfs.root / "File").stat()
        assert stat.locked is True
        assert stat.owner_read is True
        assert stat.owner_write is True

    def test_chmod_read_only(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access.R)
        stat = (adfs.root / "File").stat()
        assert stat.owner_read is True
        assert stat.owner_write is False
        assert stat.locked is False

    def test_chmod_execute_only(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Prog").write_bytes(b"code")
        (adfs.root / "Prog").chmod(Access.E)
        stat = (adfs.root / "Prog").stat()
        assert stat.owner_execute is True
        assert stat.owner_read is False
        assert stat.owner_write is False

    def test_chmod_clears_other_flags(self):
        """chmod replaces the full attribute set."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        assert (adfs.root / "File").stat().locked is True
        (adfs.root / "File").chmod(Access.R | Access.W)
        stat = (adfs.root / "File").stat()
        assert stat.locked is False
        assert stat.owner_read is True
        assert stat.owner_write is True

    def test_chmod_no_flags(self):
        """chmod with empty flags clears everything."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access(0))
        stat = (adfs.root / "File").stat()
        assert stat.owner_read is False
        assert stat.owner_write is False
        assert stat.locked is False
        assert stat.owner_execute is False

    def test_chmod_preserves_data(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"precious")
        (adfs.root / "File").chmod(Access.R | Access.L)
        assert (adfs.root / "File").read_bytes() == b"precious"

    def test_chmod_preserves_other_metadata(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(
            b"data", load_address=0x1900, exec_address=0x8023,
        )
        (adfs.root / "File").chmod(Access.R)
        stat = (adfs.root / "File").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023

    def test_chmod_on_directory(self):
        """Directories support L flag."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir").chmod(Access.L)
        stat = (adfs.root / "Dir").stat()
        assert stat.locked is True

    def test_chmod_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.chmod(Access.R)

    def test_chmod_nonexistent_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="not found"):
            (adfs.root / "Missing").chmod(Access.R)

    def test_validate_after_chmod(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access.R | Access.W | Access.L)
        assert adfs.validate() == []

    def test_chmod_sets_public_bits(self):
        """chmod sets public read/write via PR and PW flags."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access.R | Access.W | Access.PR)
        stat = (adfs.root / "File").stat()
        assert stat.public_read is True
        assert stat.public_write is False

    def test_chmod_clears_public_bits(self):
        """chmod without PR/PW clears those bits."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        # Default has public_read=True
        assert (adfs.root / "File").stat().public_read is True
        (adfs.root / "File").chmod(Access.R | Access.W)
        assert (adfs.root / "File").stat().public_read is False

    def test_default_file_attributes(self):
        """New files get WR by default (per ADFS User Guide)."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        stat = (adfs.root / "File").stat()
        assert stat.owner_read is True
        assert stat.owner_write is True
        assert stat.locked is False
        assert stat.owner_execute is False


class TestStatAccess:

    def test_default_file_access(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        stat = (adfs.root / "File").stat()
        assert stat.access == Access.R | Access.W | Access.PR

    def test_locked_file_access(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        stat = (adfs.root / "File").stat()
        assert stat.access == Access.R | Access.W | Access.L | Access.PR

    def test_read_only_access(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access.R)
        assert (adfs.root / "File").stat().access == Access.R

    def test_execute_only_access(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access.E)
        assert (adfs.root / "File").stat().access == Access.E

    def test_no_access(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").chmod(Access(0))
        assert (adfs.root / "File").stat().access == Access(0)

    def test_all_flags(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        all_flags = Access.R | Access.W | Access.L | Access.E
        (adfs.root / "File").chmod(all_flags)
        assert (adfs.root / "File").stat().access == all_flags

    def test_round_trip_chmod_stat(self):
        """chmod then stat().access should return the same flags."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        flags = Access.R | Access.L
        (adfs.root / "File").chmod(flags)
        assert (adfs.root / "File").stat().access == flags

    def test_copy_access_between_files(self):
        """stat().access from one file can be passed to chmod() on another."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Src").write_bytes(b"src")
        (adfs.root / "Src").chmod(Access.R | Access.L)
        (adfs.root / "Dst").write_bytes(b"dst")
        (adfs.root / "Dst").chmod((adfs.root / "Src").stat().access)
        assert (adfs.root / "Dst").stat().access == Access.R | Access.L

    def test_directory_access(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir").chmod(Access.L)
        assert (adfs.root / "Dir").stat().access == Access.L


class TestLockUnlockWithChmod:

    def test_lock_is_shorthand_for_adding_L(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").lock()
        stat = (adfs.root / "File").stat()
        assert stat.locked is True
        # R and W should be preserved
        assert stat.owner_read is True
        assert stat.owner_write is True

    def test_unlock_is_shorthand_for_removing_L(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        (adfs.root / "File").unlock()
        stat = (adfs.root / "File").stat()
        assert stat.locked is False
        assert stat.owner_read is True
        assert stat.owner_write is True

"""Path-level directory-entry update operations.

Covers ``AFSPath.chmod``, ``lock``, ``unlock``, ``rename``,
``set_load_address`` and ``set_exec_address`` — every operation
that mutates a directory-entry field in place without rewriting
the underlying object.  See issue #5.
"""

from __future__ import annotations

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import (
    AFSAccess,
    AFSDirectoryEntryExistsError,
    AFSDirectoryEntryNotFoundError,
    AFSPathError,
)
from oaknut.file import Access

# ---------------------------------------------------------------------------
# chmod
# ---------------------------------------------------------------------------


class TestChmod:
    def test_chmod_wire_byte_translates_to_disc(self) -> None:
        """An int argument is interpreted as the wire-form
        ``oaknut.file.Access`` byte (matching ``ADFSPath.chmod``)
        and translated to the AFS on-disc layout.
        """
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "Target"
        path.write_bytes(b"data")
        # Access.R | Access.W | Access.PR — owner R+W plus public read.
        path.chmod(int(Access.R | Access.W | Access.PR))
        got = path.stat().access
        assert got & AFSAccess.OWNER_READ
        assert got & AFSAccess.OWNER_WRITE
        assert got & AFSAccess.PUBLIC_READ
        assert not (got & AFSAccess.PUBLIC_WRITE)
        assert not (got & AFSAccess.LOCKED)

    def test_chmod_afsaccess_used_directly(self) -> None:
        """An ``AFSAccess`` argument is written to disc unchanged
        (apart from the preserved DIRECTORY bit).
        """
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "Target"
        path.write_bytes(b"data")
        new_access = AFSAccess.from_string("LR/R")
        path.chmod(new_access)
        got = path.stat().access
        assert got & AFSAccess.LOCKED
        assert got & AFSAccess.OWNER_READ
        assert got & AFSAccess.PUBLIC_READ
        assert not (got & AFSAccess.OWNER_WRITE)

    def test_chmod_accepts_plain_int_disc_form_via_afsaccess(self) -> None:
        """If callers have a disc-form byte, they can wrap it as
        ``AFSAccess.from_byte`` to pass it through verbatim.
        """
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "Target"
        path.write_bytes(b"data")
        path.chmod(AFSAccess.from_byte(0x05))  # PR + OR
        got = path.stat().access
        assert got & AFSAccess.PUBLIC_READ
        assert got & AFSAccess.OWNER_READ

    def test_chmod_preserves_directory_bit_on_directory(self) -> None:
        """Applying a file-ish wire byte to a directory must not
        strip the DIRECTORY bit.
        """
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Folder").mkdir()
        (afs.root / "Folder").chmod(int(Access.R | Access.W))
        got = (afs.root / "Folder").stat().access
        assert got & AFSAccess.DIRECTORY, "DIRECTORY bit must survive chmod"

    def test_chmod_preserves_directory_bit_on_file(self) -> None:
        """A caller trying to set the DIRECTORY bit on a file via
        ``AFSAccess`` must not actually turn the file into a dir.
        """
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "RegFile"
        path.write_bytes(b"data")
        path.chmod(AFSAccess.DIRECTORY | AFSAccess.OWNER_READ)
        got = path.stat().access
        assert not (got & AFSAccess.DIRECTORY)
        assert got & AFSAccess.OWNER_READ

    def test_chmod_rejects_root(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.chmod(int(Access.R))

    def test_chmod_rejects_missing_path(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises((AFSPathError, AFSDirectoryEntryNotFoundError)):
            (afs.root / "NoSuch").chmod(int(Access.R))


# ---------------------------------------------------------------------------
# lock / unlock
# ---------------------------------------------------------------------------


class TestLockUnlock:
    def test_lock_sets_l_bit(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data", access=AFSAccess.from_string("WR/"))
        path.lock()
        assert path.stat().access & AFSAccess.LOCKED

    def test_unlock_clears_l_bit(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data", access=AFSAccess.from_string("LR/"))
        assert path.stat().access & AFSAccess.LOCKED
        path.unlock()
        assert not (path.stat().access & AFSAccess.LOCKED)

    def test_lock_preserves_other_bits(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data", access=AFSAccess.from_string("WR/R"))
        path.lock()
        got = path.stat().access
        assert got & AFSAccess.LOCKED
        assert got & AFSAccess.OWNER_READ
        assert got & AFSAccess.OWNER_WRITE
        assert got & AFSAccess.PUBLIC_READ

    def test_unlock_preserves_other_bits(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data", access=AFSAccess.from_string("LWR/R"))
        path.unlock()
        got = path.stat().access
        assert not (got & AFSAccess.LOCKED)
        assert got & AFSAccess.OWNER_READ
        assert got & AFSAccess.OWNER_WRITE
        assert got & AFSAccess.PUBLIC_READ

    def test_lock_on_directory_preserves_directory_bit(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        (afs.root / "Dir").lock()
        got = (afs.root / "Dir").stat().access
        assert got & AFSAccess.LOCKED
        assert got & AFSAccess.DIRECTORY

    def test_lock_rejects_root(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.lock()

    def test_unlock_rejects_root(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.unlock()


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------


class TestRename:
    def test_same_directory_rename(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        src = afs.root / "Old"
        src.write_bytes(b"payload")
        new_path = src.rename("$.New")
        assert not src.exists()
        assert (afs.root / "New").exists()
        assert (afs.root / "New").read_bytes() == b"payload"
        # The returned path reflects the destination.
        assert str(new_path) == "$.New"

    def test_rename_accepts_afspath_target(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        src = afs.root / "Old"
        src.write_bytes(b"payload")
        src.rename(afs.root / "Other")
        assert (afs.root / "Other").exists()

    def test_cross_directory_rename(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "DirA").mkdir()
        (afs.root / "DirB").mkdir()
        src = afs.root / "DirA" / "f"
        src.write_bytes(b"cross-move")
        src.rename("$.DirB.g")
        assert not src.exists()
        dst = afs.root / "DirB" / "g"
        assert dst.exists()
        assert dst.read_bytes() == b"cross-move"
        # Source directory no longer lists the file.
        src_names = sorted(p.name for p in (afs.root / "DirA"))
        assert "f" not in src_names

    def test_rename_rejects_existing_target(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Old").write_bytes(b"1")
        (afs.root / "Other").write_bytes(b"2")
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "Old").rename("$.Other")

    def test_rename_rejects_missing_source(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises((AFSPathError, AFSDirectoryEntryNotFoundError)):
            (afs.root / "Nope").rename("$.NewName")

    def test_rename_rejects_root(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.rename("$.Whatever")

    def test_rename_directory(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "DirA").mkdir()
        (afs.root / "DirA" / "inner").write_bytes(b"x")
        (afs.root / "DirA").rename("$.DirZ")
        assert not (afs.root / "DirA").exists()
        assert (afs.root / "DirZ").is_dir()
        # Contents preserved.
        assert (afs.root / "DirZ" / "inner").read_bytes() == b"x"


# ---------------------------------------------------------------------------
# set_load_address / set_exec_address
# ---------------------------------------------------------------------------


class TestSetLoadExec:
    def test_set_load_address_updates_entry(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data", load_address=0x0000, exec_address=0xBEEF)
        path.set_load_address(0xCAFE)
        st = path.stat()
        assert st.load_address == 0xCAFE
        # exec_address preserved.
        assert st.exec_address == 0xBEEF

    def test_set_exec_address_updates_entry(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data", load_address=0xCAFE, exec_address=0x0000)
        path.set_exec_address(0xBEEF)
        st = path.stat()
        assert st.exec_address == 0xBEEF
        assert st.load_address == 0xCAFE

    def test_set_load_preserves_data_and_access(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"payload", access=AFSAccess.from_string("LR/R"))
        original_access = path.stat().access
        path.set_load_address(0x1234)
        assert path.read_bytes() == b"payload"
        assert path.stat().access == original_access

    def test_set_load_rejects_out_of_range(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data")
        with pytest.raises(ValueError):
            path.set_load_address(0x1_0000_0000)

    def test_set_exec_rejects_out_of_range(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "File"
        path.write_bytes(b"data")
        with pytest.raises(ValueError):
            path.set_exec_address(-1)

    def test_set_load_rejects_root(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.set_load_address(0x1000)

    def test_set_exec_rejects_root(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError, match="root"):
            afs.root.set_exec_address(0x1000)

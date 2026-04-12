"""Tests for merge bug fixes: Passwords exclusion, library target directories,
and AFS context manager flush.
"""

from __future__ import annotations

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs import merge
from oaknut.afs.libraries import SHIPPED_LIBRARIES
from oaknut.afs.passwords import PASSWORDS_FILENAME
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise


class TestMergeExcludesPasswords:
    """Bug 1: merge with conflict='overwrite' must not overwrite the
    target's Passwords file with the source's."""

    def test_merge_preserves_target_passwords(self) -> None:
        from helpers.afs_image import SyntheticFile, SyntheticUser

        # Build source with an unlocked file + its own Passwords.
        src_adfs = build_synthetic_adfs_with_afs(
            disc_name="Src",
            root_files=[SyntheticFile(name="Tool", contents=b"tool", access="R/R")],
            users=[SyntheticUser("SrcUser", system=True)],
        )
        tgt_adfs = build_synthetic_adfs_with_afs(
            disc_name="Tgt",
            root_files=[],
            users=[SyntheticUser("Syst", system=True), SyntheticUser("guest")],
        )
        src = src_adfs.afs_partition
        tgt = tgt_adfs.afs_partition

        # Source has its own Passwords.
        assert any(c.name == PASSWORDS_FILENAME for c in src.root)
        # Target has 2 users.
        assert len(tgt.users.active) == 2
        original_names = {u.name for u in tgt.users.active}

        # Merge entire source root into target root with overwrite.
        merge(tgt, src, conflict="overwrite")
        tgt.flush()

        # The target's Passwords file should NOT have been overwritten.
        tgt_reloaded = tgt_adfs.afs_partition
        assert len(tgt_reloaded.users.active) == 2
        assert {u.name for u in tgt_reloaded.users.active} == original_names
        # But the Tool file should have been copied.
        assert (tgt_reloaded.root / "Tool").read_bytes() == b"tool"


class TestEmplaceLibrary:
    """Bug 2: libraries should be emplaced into named directories."""

    def test_shipped_library_names(self) -> None:
        assert "Library" in SHIPPED_LIBRARIES
        assert "Library1" in SHIPPED_LIBRARIES
        assert "ArthurLib" in SHIPPED_LIBRARIES

    def test_initialise_creates_library_directory(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="LibTest",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Syst", system=True)],
                libraries=["Library"],
            ),
        )
        afs = adfs.afs_partition
        assert afs is not None
        lib = afs.root / "Library"
        assert lib.is_dir()
        # A known file from the Library image should be inside.
        assert (lib / "Free").exists()
        # And NOT at root.
        root_names = {c.name for c in afs.root}
        assert "Free" not in root_names

    def test_initialise_preserves_users_with_libraries(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="Users",
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("Syst", system=True),
                    UserSpec("guest"),
                ],
                libraries=["Library"],
            ),
        )
        afs = adfs.afs_partition
        assert afs is not None
        names = {u.name for u in afs.users.active}
        assert names == {"Syst", "guest"}


class TestAFSContextManager:
    """Bug 3: AFS as a context manager should auto-flush on clean exit."""

    def test_context_manager_flushes_on_exit(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with afs:
            (afs.root / "NewFile").write_bytes(b"written inside with block")

        # Re-read: the file should be visible.
        afs2 = adfs.afs_partition
        assert (afs2.root / "NewFile").read_bytes() == b"written inside with block"

    def test_context_manager_discards_on_exception(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition

        with pytest.raises(RuntimeError):
            with afs:
                (afs.root / "BadFile").write_bytes(b"will be discarded")
                raise RuntimeError("oops")

        # Re-read: the file should NOT be visible (writes discarded).
        afs2 = adfs.afs_partition
        names = {c.name for c in afs2.root}
        assert "BadFile" not in names

"""AFS.create_file orchestrator (#29).

Mirrors DFS.create_file / ADFS.create_file as a single top-level
constructor for a brand-new AFS image — composes ADFS.create_file +
initialise + emplace_library so callers don't have to.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.afs import AFS, UserSpec


class TestAFSCreateFile:
    def test_creates_empty_afs_image(self, tmp_path: Path) -> None:
        filepath = tmp_path / "server.dat"
        with AFS.create_file(filepath, capacity="5MB", disc_name="EmptyAFS") as afs:
            assert afs.disc_name == "EmptyAFS"
            # Default users — Syst, Boot, Welcome.
            names = {user.name for user in afs.users.active}
            assert names == {"Syst", "Boot", "Welcome"}

    def test_creates_with_extra_user(self, tmp_path: Path) -> None:
        filepath = tmp_path / "server.dat"
        with AFS.create_file(
            filepath,
            capacity="5MB",
            disc_name="WithUser",
            users=[UserSpec("RJS", quota="2MB")],
        ) as afs:
            names = {user.name for user in afs.users.active}
            assert "RJS" in names

    def test_omit_welcome(self, tmp_path: Path) -> None:
        filepath = tmp_path / "server.dat"
        with AFS.create_file(
            filepath,
            capacity="5MB",
            disc_name="NoWelcome",
            omit_users=["Welcome"],
        ) as afs:
            names = {user.name for user in afs.users.active}
            assert "Welcome" not in names
            assert {"Syst", "Boot"} <= names

    def test_emplaces_library(self, tmp_path: Path) -> None:
        filepath = tmp_path / "server.dat"
        with AFS.create_file(
            filepath,
            capacity="10MB",
            disc_name="WithLib",
            emplacements=["Library"],
        ) as afs:
            assert (afs.root / "Library").is_dir()

    def test_file_persists_after_context(self, tmp_path: Path) -> None:
        filepath = tmp_path / "server.dat"
        with AFS.create_file(filepath, capacity="5MB", disc_name="Persist"):
            pass
        # Reopen the image and confirm AFS init survived.
        with AFS.from_file(filepath) as afs:
            assert afs.disc_name == "Persist"

    def test_capacity_int_bytes(self, tmp_path: Path) -> None:
        filepath = tmp_path / "server.dat"
        with AFS.create_file(filepath, capacity=5_000_000, disc_name="IntCap"):
            pass
        with AFS.from_file(filepath) as afs:
            assert afs.disc_name == "IntCap"

    def test_mutations_inside_context_persist(self, tmp_path: Path) -> None:
        """A clean exit from AFS.create_file flushes pending writes.

        Without this, mutations made via AFSPath inside the
        ``with`` block stay in the in-memory ``_pending_writes`` buffer
        and never reach the underlying disc — silently lost on close.
        """
        filepath = tmp_path / "server.dat"
        with AFS.create_file(filepath, capacity="5MB", disc_name="Inside") as afs:
            (afs.root / "Made").mkdir()
            (afs.root / "Made" / "Note").write_text("hello\n")

        with AFS.from_file(filepath) as afs:
            assert (afs.root / "Made" / "Note").read_text() == "hello\n"


class TestAFSFromFile:
    def test_mutations_inside_context_persist(self, tmp_path: Path) -> None:
        """A clean exit from AFS.from_file flushes pending writes.

        Mirrors :meth:`AFS.__exit__` behaviour: callers should not need
        to call :meth:`AFS.flush` explicitly inside the ``with`` block.
        """
        filepath = tmp_path / "server.dat"
        with AFS.create_file(filepath, capacity="5MB", disc_name="Reopen"):
            pass

        with AFS.from_file(filepath, mode="r+b") as afs:
            afs.add_user("alice", quota="1MB")

        with AFS.from_file(filepath) as afs:
            names = {user.name for user in afs.users.active}
            assert "alice" in names

    def test_exception_inside_context_discards(self, tmp_path: Path) -> None:
        """An exception inside AFS.from_file rolls back pending writes."""
        filepath = tmp_path / "server.dat"
        with AFS.create_file(filepath, capacity="5MB", disc_name="Rollback"):
            pass

        with pytest.raises(RuntimeError):
            with AFS.from_file(filepath, mode="r+b") as afs:
                afs.add_user("ghost", quota="1MB")
                raise RuntimeError("boom")

        with AFS.from_file(filepath) as afs:
            names = {user.name for user in afs.users.active}
            assert "ghost" not in names

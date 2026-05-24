"""Add a user account to an existing AFS image.

Demonstrates :meth:`AFS.add_user` — the public counterpart to the CLI's
``disc afs-useradd``. The ``quota`` keyword takes the same
capacity-string form as :meth:`AFS.create_file` (``"2MB"``, ``"512KiB"``)
so a setup script doesn't have to hand-compute byte counts.

The recipe builds an AFS disc with just the built-in accounts, then
opens it read-write and tacks on a fresh user.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.afs import AFS


def add_user(image_filepath: Path, username: str, quota: str) -> None:
    """Open *image_filepath* read-write and add *username* with *quota*.

    Composes :meth:`AFS.add_user` with the read-write
    :meth:`AFS.from_file` context manager. The flush on context exit
    propagates the new passwords record to disc.
    """
    with AFS.from_file(image_filepath, mode="r+b") as afs:
        afs.add_user(username, quota=quota)
        afs.flush()


def _build_empty_server(workdir: Path) -> Path:
    filepath = workdir / "server.dat"
    with AFS.create_file(filepath, capacity="5MB", disc_name="MyServer"):
        pass
    return filepath


def main(workdir: Path) -> None:
    filepath = _build_empty_server(workdir)
    add_user(filepath, "alice", quota="2MB")

    # Confirm the user appeared with the right quota.
    with AFS.from_file(filepath) as afs:
        alice = next(u for u in afs.users.active if u.name == "alice")
        print(f"Added user: {alice.name}  quota={alice.free_space:,} bytes")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

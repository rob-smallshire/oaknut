"""Add a user account to the AFS partition of an ADFS hard-disc image.

An AFS file server lives in the tail of an ADFS hard-disc image —
there is no standalone AFS image — so the recipe opens the disc as
ADFS and reaches into the AFS partition through
:attr:`oaknut.adfs.ADFS.afs_partition`. The two contexts compose so
the AFS handle's pending writes flush on clean exit and roll back on
exception, all inside the surrounding ADFS lifetime.

:meth:`AFS.add_user` mirrors the CLI's ``disc afs-useradd``. The
``quota`` keyword takes the same capacity-string form as
:meth:`AFS.create_file` (``"2MB"``, ``"512KiB"``) so a setup script
does not have to hand-compute byte counts.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.adfs import ADFS
from oaknut.afs import AFS


def add_user(disc_filepath: Path, username: str, quota: str) -> None:
    """Add username with quota to the AFS partition on the given disc.

    The disc is opened as ADFS; ``adfs.afs_partition`` yields the AFS
    handle. Writes are buffered on the AFS side and flushed when the
    ``with`` block exits cleanly; an exception inside the block
    discards them, leaving the on-disc passwords file untouched.

    Args:
        disc_filepath: ADFS hard-disc image (``.dat`` + ``.dsc``
            sidecar) whose tail carries the AFS partition.
        username: Name of the account to add. Must not already exist.
        quota: Capacity string (``"2MB"``, ``"512KiB"``, ...) or raw
            int byte count.
    """
    with ADFS.from_file(disc_filepath) as adfs, adfs.afs_partition as afs:
        afs.add_user(username, quota=quota)


def _build_empty_server(workdir: Path) -> Path:
    filepath = workdir / "server.dat"
    with AFS.create_file(filepath, capacity="5MB", disc_name="MyServer"):
        pass
    return filepath


def main(workdir: Path) -> None:
    filepath = _build_empty_server(workdir)
    add_user(filepath, "alice", quota="2MB")

    with ADFS.from_file(filepath) as adfs, adfs.afs_partition as afs:
        alice = next(u for u in afs.users.active if u.name == "alice")
        print(f"Added user: {alice.name}  quota={alice.free_space:,} bytes")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

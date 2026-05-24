"""Build a bootable Level 3 File Server disc end-to-end.

AFS.create_file is the orchestrator: one call creates the ADFS
envelope, initialises the AFS partition, lays down the user accounts,
and emplaces shipped library images. The same configuration through
the lower-level building blocks would be 20 lines of composition.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.afs import AFS, UserSpec


def build_server_disc(filepath: Path) -> None:
    """Create a 10 MB L3FS hard disc with a custom user and one library.

    The capacity="10MB" string saves the caller from manual byte
    arithmetic; the users and emplacements arguments turn what used
    to be a four-import composition into a single call site.

    Args:
        filepath: Destination .dat path. The companion .dsc sidecar
            is written automatically.
    """
    with AFS.create_file(
        filepath,
        capacity="10MB",
        disc_name="MyServer",
        users=[UserSpec("RJS", quota="2MB")],
        omit_users=["Welcome"],
        emplacements=["Library"],
    ) as afs:
        # The yielded AFS handle is open and writable — drop a personal
        # boot file into the new RJS user's home directory equivalent.
        (afs.root / "RJS").mkdir()
        (afs.root / "RJS" / "Notes").write_text(
            "server built via AFS.create_file",
        )


def main(workdir: Path) -> None:
    filepath = workdir / "server.dat"
    build_server_disc(filepath)

    # Re-open and report the final state.
    with AFS.from_file(filepath) as afs:
        print(f"Disc:    {afs.disc_name}")
        print(f"Free:    {afs.free_sectors} sectors")
        print("Users:")
        for user in afs.users.active:
            kind = "system" if user.is_system else "user  "
            print(f"  {kind}  {user.name}")
        print("Root:")
        for entry in sorted(afs.root.iterdir(), key=lambda p: p.name):
            tag = "dir" if entry.is_dir() else "file"
            print(f"  {tag}  {entry.name}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

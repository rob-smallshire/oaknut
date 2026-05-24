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
    """Create a 10 MB L3FS hard disc with one custom user and one library.

    Args:
        filepath: Destination .dat path. The companion .dsc sidecar
            is written automatically.
    """
    herman_username = "Herman"
    with AFS.create_file(
        filepath,
        capacity="10MB",
        disc_name="MyServer",
        users=[UserSpec(herman_username, quota="2MB")],
        omit_users=["Welcome"],
        emplacements=["Library"],
    ) as afs:
        # initialise() laid down a User Root Directory for Herman as
        # part of account creation, so we can write straight into it.
        herman_user_root_dirpath = afs.root / herman_username
        (herman_user_root_dirpath / "Notes").write_text(
            "server built via AFS.create_file\n",
        )


def main(workdir: Path) -> None:
    filepath = workdir / "server.dat"
    build_server_disc(filepath)

    # Re-open and confirm every part of the build landed on disc.
    with AFS.from_file(filepath) as afs:
        names = {user.name for user in afs.users.active}
        assert "Herman" in names
        assert "Welcome" not in names
        assert (afs.root / "Library").is_dir()
        assert (afs.root / "Herman" / "Notes").read_text().startswith(
            "server built via AFS.create_file"
        )

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

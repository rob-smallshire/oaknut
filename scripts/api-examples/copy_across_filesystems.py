"""Copy a file from a DFS floppy onto an ADFS hard disc.

Demonstrates copy_to, the sugar over oaknut.file.copy_file. The
source path knows how to read itself and the destination path knows
how to write its native metadata, so the caller writes one line and
the access bits map across the filesystem boundary automatically.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.adfs import ADFS
from oaknut.dfs import DFS
from oaknut.file import Access


def cross_copy(source_filepath: Path, target_filepath: Path) -> None:
    """Copy every file from a DFS floppy into the root of an ADFS image.

    The DFS catalogue is flat (single-character directory tags), the
    ADFS root is a real directory; copy_to does the right thing on
    both ends without the caller spelling out the conversion.

    Args:
        source_filepath: DFS .ssd or .dsd image to copy from.
        target_filepath: ADFS image (.dat or .adl) to copy into.
            Opened read-write; the source is opened read-only.
    """
    with (
        DFS.from_file(source_filepath) as dfs,
        ADFS.from_file(target_filepath) as adfs,
    ):
        for letter in dfs.root.iterdir():
            for entry in letter.iterdir():
                # ADFS filenames are <= 10 chars and case-preserving;
                # DFS gives us 7-char uppercase names that already fit.
                destination = adfs.root / entry.name
                entry.copy_to(destination)


def _build_source_floppy(workdir: Path) -> Path:
    filepath = workdir / "games.ssd"
    with DFS.create_file(filepath, title="Games") as dfs:
        (dfs.root / "$.HELLO").write_text(
            'PRINT "Hello"\n', load_address=0x1900
        )
        (dfs.root / "$.LOCKED").write_text("keep\n", access=Access.LWR)
        (dfs.root / "A.NOTES").write_text("sibling-dir note\n")
    return filepath


def _build_target_hd(workdir: Path) -> Path:
    filepath = workdir / "archive.dat"
    with ADFS.create_file(filepath, capacity="5MB", title="Archive"):
        pass
    return filepath


def main(workdir: Path) -> None:
    source = _build_source_floppy(workdir)
    target = _build_target_hd(workdir)
    cross_copy(source, target)
    # Confirm the copy by reading back from the target.
    with ADFS.from_file(target) as adfs:
        for entry in sorted(adfs.root.iterdir(), key=lambda p: p.name):
            st = entry.stat()
            print(f"  {entry.name:10s}  size={st.length:>5d}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

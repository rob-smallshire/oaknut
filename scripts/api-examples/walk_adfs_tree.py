"""Walk an ADFS directory tree recursively.

ADFS is hierarchical — unlike DFS's flat catalogue — so the natural
read pattern is recursive iteration. walk_tree below is the
equivalent of os.walk for an ADFS image and works identically against
AFS via AFSPath.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable

from oaknut.adfs import ADFS, ADFS_L


def walk_tree(start: "ADFSPath", indent: str = "") -> None:  # noqa: F821
    """Print an ADFS subtree with two-space indentation per level.

    Demonstrates ADFSPath.iterdir, is_dir for branch selection, and
    the natural recursion the hierarchical model invites. The same
    code works against AFSPath without modification.

    Args:
        start: Path to walk from. Usually adfs.root for the whole tree.
        indent: Current indentation prefix. Used by the recursive call;
            callers typically leave it at the default empty string.
    """
    print(f"{indent}{start.name}/")
    for child in sorted(start.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
        if child.is_dir():
            walk_tree(child, indent + "  ")
        else:
            st = child.stat()
            print(f"{indent}  {child.name:18s}  {st.length:>6d}")


def _build_demo_tree(workdir: Path) -> Path:
    """Build a small ADFS image with a nested directory tree."""
    filepath = workdir / "demo.adl"
    with ADFS.create_file(filepath, ADFS_L, title="Demo") as adfs:
        (adfs.root / "ReadMe").write_text("top-level note\r")
        (adfs.root / "Code").mkdir()
        (adfs.root / "Code" / "Main").write_bytes(b"\x00" * 200)
        (adfs.root / "Code" / "Utils").mkdir()
        (adfs.root / "Code" / "Utils" / "Sort").write_bytes(b"\x00" * 50)
        (adfs.root / "Docs").mkdir()
        (adfs.root / "Docs" / "Manual").write_text("manual\r")
    return filepath


def main(workdir: Path) -> None:
    filepath = _build_demo_tree(workdir)
    with ADFS.from_file(filepath) as adfs:
        walk_tree(adfs.root)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

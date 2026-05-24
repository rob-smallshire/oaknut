"""Walk an ADFS directory tree recursively.

ADFS (and AFS) is hierarchical, so the natural read pattern is a
tree walk. ADFSPath.walk and AFSPath.walk both mirror
pathlib.Path.walk: each step yields ``(dirpath, dirnames, filenames)``
in pre-order, descending into every subdirectory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.adfs import ADFS, ADFS_L


def walk_tree(start) -> None:
    """Print an ADFS subtree with two-space indentation per level.

    Args:
        start: Path to walk from. Usually adfs.root for the whole tree.
    """
    root_depth = len(start.parts)
    for dirpath, dirnames, filenames in start.walk():
        indent = "  " * (len(dirpath.parts) - root_depth)
        print(f"{indent}{dirpath.name}/")
        for filename in filenames:
            size = (dirpath / filename).stat().length
            print(f"{indent}  {filename:18s}  {size:>6d}")


def _build_demo_tree(workdir: Path) -> Path:
    """Build a small ADFS image with a nested directory tree."""
    filepath = workdir / "demo.adl"
    with ADFS.create_file(filepath, ADFS_L, title="Demo") as adfs:
        (adfs.root / "ReadMe").write_text("top-level note\n")
        (adfs.root / "Code").mkdir()
        (adfs.root / "Code" / "Main").write_bytes(b"\x00" * 200)
        (adfs.root / "Code" / "Utils").mkdir()
        (adfs.root / "Code" / "Utils" / "Sort").write_bytes(b"\x00" * 50)
        (adfs.root / "Docs").mkdir()
        (adfs.root / "Docs" / "Manual").write_text("manual\n")
    return filepath


def main(workdir: Path) -> None:
    filepath = _build_demo_tree(workdir)
    with ADFS.from_file(filepath) as adfs:
        walk_tree(adfs.root)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

"""Enumerate the filesystem packages installed in this environment.

:func:`~oaknut.filesystem.filesystem_names` and
:func:`~oaknut.filesystem.describe_filesystem` are the discovery surface
for tools that adapt to what is present rather than assuming a fixed
set. The result reflects whatever ``oaknut.filesystem`` entry points
the current Python environment can see; installing or uninstalling a
filesystem package changes the list automatically — no hand-wired
registry to edit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.filesystem import describe_filesystem, filesystem_names


def list_installed() -> None:
    """Print every recognised filesystem with its one-line description."""
    for name in sorted(filesystem_names()):
        print(f"  {name:14s}  {describe_filesystem(name, single_line=True)}")


def main(workdir: Path) -> None:
    """Run the recipe — no fixture needed; the answer is environment-only."""
    del workdir
    list_installed()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

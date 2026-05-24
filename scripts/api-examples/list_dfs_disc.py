"""Open a DFS disc image and list its contents.

The interesting bit is :func:`list_disc` — every other line below is
just so the script can run on its own and the test suite can exercise
it without external corpus images.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.dfs import DFS
from oaknut.file import Access


def list_disc(filepath: Path) -> None:
    """List every file on a DFS image: name, locked flag, length, load address.

    Demonstrates auto-detected format on ``DFS.from_file``, two-level
    iteration through the catalogue's directory letters, and the
    unified :class:`oaknut.file.Stat` protocol's ``.access``,
    ``.length``, ``.load_address`` accessors.
    """
    with DFS.from_file(filepath) as dfs:
        print(f"Title: {dfs.title}")
        for directory in dfs.root.iterdir():
            for entry in directory.iterdir():
                st = entry.stat()
                lock = "L" if st.access & Access.L else " "
                print(
                    f"  {entry.path:14s}  {lock}  "
                    f"load={st.load_address:#010x}  "
                    f"size={st.length:>6d}"
                )


def _build_demo_disc(workdir: Path) -> Path:
    """Build a small fresh disc so the listing has something to show."""
    filepath = workdir / "demo.ssd"
    with DFS.create_file(filepath, title="Demo") as dfs:
        (dfs.root / "$.HELLO").write_bytes(
            b'10 PRINT "Hello"\r20 END\r',
            load_address=0x1900,
            exec_address=0x1900,
        )
        (dfs.root / "$.LOCKED").write_bytes(b"\x00" * 256, access=Access.LWR)
        (dfs.root / "A.GAME").write_bytes(b"\x00" * 100, load_address=0x3000)
    return filepath


def main(workdir: Path) -> None:
    """Run the recipe: build a demo disc, then list its contents."""
    list_disc(_build_demo_disc(workdir))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

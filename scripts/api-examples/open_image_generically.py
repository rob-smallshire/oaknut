"""Open any disc image through the coordinator and list it generically.

Demonstrates the content-first open flow — identify → create_filesystem
→ reader_for → ``filesystem.open`` — and then the filesystem-agnostic
:class:`~oaknut.filesystem.Mount` core (``iter_entries``, ``stat``,
``read_bytes``). The ``isinstance`` checks against capability protocols
(:class:`~oaknut.filesystem.Titled`,
:class:`~oaknut.filesystem.Bootable`,
:class:`~oaknut.filesystem.AcornMetadata`) opt the same code into
disc-level behaviour where the underlying filesystem supports it, and
quietly skip it where it does not.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.dfs import DFS
from oaknut.file import Access
from oaknut.filesystem import (
    AcornMetadata,
    Bootable,
    Titled,
    create_filesystem,
    identify,
    reader_for,
)


def walk_any_disc(filepath: Path) -> None:
    """Walk any recognised disc one directory deep, with disc-level details.

    The same function works against a DFS floppy, an ADFS hard disc,
    an AFS partition, or a ZIP archive — the mount's core is uniform
    and the capability checks adapt the rest.

    Args:
        filepath: Any disc image.
    """
    candidates = identify(filepath)
    if not candidates:
        print(f"{filepath.name}: nothing recognised")
        return
    choice = candidates[0]

    filesystem = create_filesystem(choice.filesystem)
    with reader_for(filepath) as reader:
        mount = filesystem.open(reader, choice.geometry)

        if isinstance(mount, Titled):
            print(f"Title: {mount.title}")
        if isinstance(mount, Bootable):
            print(f"Boot option: {mount.boot_option.name}")

        def _show(entry, indent: int) -> None:
            kind = "dir " if entry.is_dir else "file"
            line = f"{'  ' * (indent + 1)}{entry.name:14s} {kind}  size={entry.length}"
            if isinstance(mount, AcornMetadata) and not entry.is_dir:
                meta = mount.acorn_meta(entry.path)
                if meta.load_address is not None:
                    line += f"  load={meta.load_address:#010x}"
            print(line)

        for top in mount.iter_entries(mount.path_root()):
            _show(top, indent=0)
            if top.is_dir:
                for child in mount.iter_entries(top.path):
                    _show(child, indent=1)


def _build_demo_disc(workdir: Path) -> Path:
    """A small DFS disc with two files, enough to show the iteration shape."""
    filepath = workdir / "demo.ssd"
    with DFS.create_file(filepath, title="Demo") as dfs:
        (dfs.root / "$.HELLO").write_text(
            '10 PRINT "Hello"\n20 END\n', load_address=0x1900, exec_address=0x1900
        )
        (dfs.root / "$.LOCKED").write_bytes(b"\x00" * 256, access=Access.LWR)
    return filepath


def main(workdir: Path) -> None:
    """Run the recipe against a freshly-built demo disc."""
    walk_any_disc(_build_demo_disc(workdir))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

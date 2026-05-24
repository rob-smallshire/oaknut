"""Create a DFS floppy with several entries and varied metadata.

Shows DFS.create_file (format defaulted from the .ssd extension),
write_bytes and write_text, varied load/exec addresses, and the
canonical locked-file pattern (access=Access.LWR).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.dfs import DFS
from oaknut.file import Access, BootOption


def populate_disc(filepath: Path) -> None:
    """Lay down four entries that exercise the write surfaces.

    The entries:

    - $.README — plain text, Acorn-encoded by write_text. The default
      load/exec of 0 is fine for data files.
    - $.PROG — raw program bytes loaded at the BBC's canonical 0x1900,
      auto-running on *RUN.
    - $.DATA — arbitrary bytes at a non-default load address.
    - $.LOCKED — small file, locked via the named composite Access.LWR
      (locked + owner R+W).
    """
    with DFS.create_file(filepath, title="MyDisc", boot_option=2) as dfs:
        (dfs.root / "$.README").write_text(
            "Welcome to MyDisc.\r"
            "Run *EXEC $.README at the prompt.\r",
        )
        (dfs.root / "$.PROG").write_bytes(
            b"\xa9\x41\x20\xee\xff\x60",   # LDA #'A' : JSR &FFEE : RTS
            load_address=0x1900,
            exec_address=0x1900,
        )
        (dfs.root / "$.DATA").write_bytes(
            bytes(range(64)),
            load_address=0x3000,
        )
        (dfs.root / "$.LOCKED").write_bytes(
            b"do not delete\r",
            access=Access.LWR,
        )


def main(workdir: Path) -> None:
    filepath = workdir / "MyDisc.ssd"
    populate_disc(filepath)

    # Round-trip: re-open and confirm the entries landed with the
    # metadata we set.
    with DFS.from_file(filepath) as dfs:
        print(f"Title:       {dfs.title}")
        print(f"Boot option: {BootOption(dfs.boot_option).name}")
        for letter in dfs.root.iterdir():
            for entry in letter.iterdir():
                st = entry.stat()
                lock = " (locked)" if st.access & Access.L else ""
                print(
                    f"  {entry.path:14s} "
                    f"load={st.load_address:#010x} "
                    f"size={st.length:>5d}{lock}"
                )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

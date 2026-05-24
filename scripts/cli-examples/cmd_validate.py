"""Example for ``disc validate`` — image-structure consistency check.

Shows both outcomes so the contract is unambiguous: a clean image
produces no output and exits 0 (silence is the success signal); a
damaged image prints one ``Error: ...`` line per defect to stderr,
followed by an ``N error(s) found`` summary, and exits 65
(``EX_DATAERR``).

The damaged image is forged in-recipe by writing a DFS catalogue
that places two files at the same start sector — something the
public API would refuse to construct, which is the point.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402


def _write_broken_dfs_image(target: Path) -> None:
    """Forge a 40T SSD with two catalogue entries pointing at sector 2."""
    buf = bytearray(102400)
    buf[0:8] = b"BROKEN  "
    buf[256:260] = b"    "
    buf[260] = 0
    buf[261] = 16  # 2 files in catalogue
    buf[262] = 0x00
    buf[263] = 200
    # File $.A at sector 2
    buf[8:15] = b"A      "
    buf[15] = ord("$")
    buf[256 + 8 : 256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])
    # File $.B at sector 2 — overlap
    buf[16:23] = b"B      "
    buf[23] = ord("$")
    buf[256 + 16 : 256 + 24] = bytes([0, 0, 0, 0, 100, 0, 0, 2])
    target.write_bytes(bytes(buf))


with in_tmp_dir():
    section("clean")
    silent("disc create clean.adl --title Demo")
    show("disc validate clean.adl 2>&1; echo exit=$?")

    section("damaged")
    _write_broken_dfs_image(Path("bad.ssd"))
    show("disc validate bad.ssd 2>&1; echo exit=$?")

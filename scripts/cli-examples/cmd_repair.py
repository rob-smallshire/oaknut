"""Example for ``disc repair`` — fix the defects ``disc validate`` finds.

The disc is a stand-in for the PanOS 1.40 installation discs: a sound
80-track double-sided DFS disc whose two catalogues carry malformed
sector counts (bit 2 of &106 set, declaring 1600 and 1503 sectors on
800-sector sides), trimmed short of a full disc as those images are.
``validate`` reports the defect on each drive; ``repair --dry-run`` says
what it would change; ``repair`` changes it; ``validate`` is then silent.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, show_error, silent  # noqa: E402

_SIDE_1_CATALOGUE = 0xA00  # track 0 of side 1 in an interleaved DSD


def _malform(image: Path) -> None:
    """Give both catalogues the PanOS discs' sector counts, and trim the image."""
    raw = bytearray(image.read_bytes())
    raw[0x106], raw[0x107] = 0x36, 0x40
    raw[_SIDE_1_CATALOGUE + 0x106], raw[_SIDE_1_CATALOGUE + 0x107] = 0x35, 0xDF
    image.write_bytes(bytes(raw[:407040]))


with in_tmp_dir():
    # Prepared in advance: a two-sided installation disc.
    Path("installer").write_bytes(b"*RUN Install\r")
    silent("disc create install.dsd --title Install")
    silent("disc put 'install.dsd:$.!Boot' installer")
    silent("disc put 'install.dsd::2.$.Extras' installer")
    _malform(Path("install.dsd"))

    section("validate")
    show_error("disc validate install.dsd", returncode=65)

    section("dry_run")
    show("disc repair --dry-run install.dsd")

    section("repair")
    show("disc repair install.dsd")
    show("disc validate install.dsd")

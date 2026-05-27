"""Browse a ZIP archive through ``disc`` — ZIP is a filesystem too.

Builds a small archive of RISC OS files whose filetypes are carried in
the ``,xxx`` filename suffix, then identifies, lists, and extracts from
it with the same commands used on a real disc. The recovered metadata
surfaces in the listing and in the ``.inf`` sidecar ``disc get`` writes.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show  # noqa: E402

with in_tmp_dir():
    with zipfile.ZipFile("riscos.zip", "w") as archive:
        archive.writestr("!Boot,feb", b"| boot\n")
        archive.writestr("Sprites,ff9", b"sprite data")
        archive.writestr("Docs/ReadMe,fff", b"Hello from RISC OS\n")
        archive.writestr("Docs/Manual,fff", b"chapter one\n")

    section("identify")
    show("disc identify riscos.zip")

    section("ls")
    show("disc ls riscos.zip")

    section("tree")
    show("disc tree riscos.zip")

    section("get")
    show("disc get 'riscos.zip:Sprites' Sprites")
    show("cat Sprites.inf")

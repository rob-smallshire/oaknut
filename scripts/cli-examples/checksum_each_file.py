"""Cookbook recipe: a TSV of (path, checksum) for every file on a disc.

Three stages, each its own ``section()``:

- ``cksum``         — CRC32 + byte count; clean output, computable on
                      the BBC Micro itself so a host-side table can be
                      verified against the original hardware.
- ``md5sum``        — cryptographic hash; introduces ``md5sum``'s
                      ``  -`` stdin marker as a teachable artefact.
- ``md5sum-trim``   — shell wrapper that trims the marker, for a
                      ``path \\t hash`` table when that's what you want.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create archive.ssd --title Backup")
    silent("printf 'Welcome to the BACKUP disc.\\r' | disc put 'archive.ssd:$.README' -")
    silent("printf 'CHAIN \"LOADER\"\\r' | disc put 'archive.ssd:$.!BOOT' -")
    silent("head -c 256 /dev/zero | disc put 'archive.ssd:$.LOADER' -")
    silent("head -c 4096 /dev/zero | disc put 'archive.ssd:$.GAME' -")

    section("cksum")
    show("disc for-each 'archive.ssd:*' -- cksum")

    section("md5sum")
    show("disc for-each 'archive.ssd:*' -- md5sum")

    section("md5sum-trim")
    show("disc for-each 'archive.ssd:*' -- sh -c 'md5sum | cut -d \" \" -f 1'")

"""Cookbook recipe: TSV of (path, md5) for every file on a disc.

Builds a small DFS image with a few files of varied content, then runs
the headline ``disc for-each`` invocation that piped-stdin commands
were designed for: each file's bytes through ``md5sum``, the path /
checksum pairs aggregated into a clean TSV. The ``sh -c 'md5sum | cut'``
wrapper strips ``md5sum``'s ``  -`` stdin marker so each row holds just
the hash.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create archive.ssd --title Backup")
    silent("printf 'Welcome to the BACKUP disc.\\r' | disc put 'archive.ssd:$.README' -")
    silent("printf 'CHAIN \"LOADER\"\\r' | disc put 'archive.ssd:$.!BOOT' -")
    silent("head -c 256 /dev/zero | disc put 'archive.ssd:$.LOADER' -")
    silent("head -c 4096 /dev/zero | disc put 'archive.ssd:$.GAME' -")

    show(
        "disc for-each 'archive.ssd:*' --as tsv "
        "-- sh -c 'md5sum | cut -d \" \" -f 1'"
    )

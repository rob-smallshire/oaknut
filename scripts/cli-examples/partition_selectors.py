"""Partition selectors and content-first identification on a combined disc.

Renders the "Partition selectors" section of
``docs/disc/cli/conventions/paths.rst`` and the partitioned-disc
``disc find`` block in ``docs/disc/cli/conventions/wildcards.rst``,
using the shipped Level 3 File Server image — a real ADFS hard disc
that carries an AFS tail partition.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import (  # noqa: E402
    in_tmp_dir,
    section,
    show,
    show_error,
    silent,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMBINED = REPO_ROOT / "tests" / "data" / "images" / "l3fs" / "l3fs-wfsinit.dat"

with in_tmp_dir():
    shutil.copy(COMBINED, "scsi0.dat")

    # Selecting a partition by its filesystem key. With no selector the
    # best-identified partition (the ADFS host) is mounted.
    section("selectors")
    show("disc ls scsi0.dat")
    show("disc ls 'scsi0.dat:adfs:$'")
    show("disc ls 'scsi0.dat:afs:$'")

    # `disc find` prefixes each hit with the selector that addresses it.
    section("find")
    show("disc find 'scsi0.dat:*'")

    # Content the identifier does not recognise.
    section("unrecognised")
    silent("printf 'not an Acorn disc image' > some.image")
    show_error("disc ls some.image")

    # A selector the image cannot satisfy: a plain DFS disc has only an
    # acorn-dfs partition.
    section("wrong_partition")
    silent("disc create games.ssd --title GAMES")
    show_error("disc ls 'games.ssd:adfs:$'")

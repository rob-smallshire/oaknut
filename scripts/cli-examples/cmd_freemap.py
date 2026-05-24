"""Example for ``disc freemap`` — 2-D fragmentation grid.

Builds a small 40-track DFS floppy with a handful of files, then
deletes a mid-disc ``LOADER`` to leave a visible hole. The 40T
geometry keeps the rendered grid compact (40 rows × 10 columns)
while still showing both used (``█``) and free (``.``) sectors —
and the deleted-file hole is the visual payoff that justifies a
2-D layout.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create --format ssd --tracks 40 --title Planet planet.ssd")
    silent("head -c 12 /dev/zero | disc put 'planet.ssd:$.!BOOT' -")
    silent("head -c 2304 /dev/zero | disc put 'planet.ssd:$.LOADER' -")
    silent("head -c 9216 /dev/zero | disc put 'planet.ssd:$.PLANET' -")
    silent("head -c 100 /dev/zero | disc put 'planet.ssd:$.HISCORE' -")
    silent("disc rm 'planet.ssd:$.LOADER'")
    show("disc freemap planet.ssd")

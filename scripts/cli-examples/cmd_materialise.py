"""Example for ``disc materialise`` — host-tempfile a single in-image file.

`materialise` reads the addressed file from the image, writes its bytes
to a host temp file, substitutes ``{}`` in the command with that path
(or appends it if absent), runs the command, and cleans up — so a
host-native tool that only takes regular files (``file``, image
viewers, emulators) can be pointed at an in-image file without manual
extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --title Demo")
    silent("printf 'hello world\\n' | disc put 'demo.ssd:$.README' -")
    show("disc materialise 'demo.ssd:$.README' -- file {}")

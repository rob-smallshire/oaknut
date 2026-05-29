"""Assemble a double-sided DSD from two single-sided SSDs.

A real-world recipe: you have two DFS ``.ssd`` floppy images and want
them combined onto one double-sided ``.dsd`` — one game per side, as a
double-sided disc would have been pressed. ``disc create`` lays down a
blank DSD (formatting *both* sides), then a ``disc cp`` per side copies
each SSD's catalogue onto it. The second side is addressed with verbatim
Acorn drive syntax, ``image::2.$``.

Sections:

  sources   ``ls`` — the two single-sided source SSDs.
  create    ``disc create`` — a blank double-sided DSD; both sides are
            formatted as empty catalogues.
  copy      One ``disc cp`` per side: side 0 (drive ``:0``, the default)
            and side 2 (drive ``:2``). Each side gets its own title.
  verify    ``disc stat`` lists both sides; ``disc ls`` shows each
            side's catalogue under its drive designation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GAMES_DIR = REPO_ROOT / "tests" / "data" / "images" / "games"

with in_tmp_dir():
    # Bring two SSDs into the working directory under short names so the
    # captured command lines stay free of absolute paths.
    silent(f"cp {GAMES_DIR}/Disc002-Arcadians.ssd arcadians.ssd")
    silent(f"cp {GAMES_DIR}/Disc003-Zalaga.ssd zalaga.ssd")

    section("sources")
    show("disc ls arcadians.ssd:\\$")
    show("disc ls zalaga.ssd:\\$")

    section("create")
    show("disc create compendium.dsd --title Arcadians")

    section("copy")
    # Side 0 is the default — a bare path needs no drive. Side 2 is the
    # second physical surface, addressed ::2. The `$.*` glob copies every
    # file in the source's `$` directory; the trailing `/` on the
    # destination marks it as a directory to copy into.
    show("disc cp 'arcadians.ssd:$.*' 'compendium.dsd:$/'")
    show("disc cp 'zalaga.ssd:$.*' 'compendium.dsd::2.$/'")
    # Each side is an independent volume with its own title. Addressing a
    # side's disc title takes the drive with no path (``::2``); ``::2.$``
    # would instead ask for the ``$`` directory's title, which DFS lacks.
    show("disc title 'compendium.dsd::2' Zalaga")

    section("verify")
    show("disc stat compendium.dsd")
    show("disc ls compendium.dsd:\\$")
    show("disc ls 'compendium.dsd::2.$'")

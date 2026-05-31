"""Files whose names contain wildcard characters.

A DFS catalogue can hold names like ``guard#1`` even though ``#`` is the
single-character wildcard at the command line — the game Guardian ships
``guard#1`` and ``guard#2`` on its disc. This recipe creates such files,
copies a whole disc that contains them, and shows how ``--no-wildcards``
addresses one of them literally when a glob would otherwise sweep up a
same-shaped neighbour (``guard41``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    # Prepared in advance: a Guardian disc that already holds the two
    # ordinarily-named files guard41 and guard42.
    Path("payload").write_bytes(b"Guardian game data.\r")
    silent("disc create guardian.ssd --title GUARDIAN")
    silent("disc put 'guardian.ssd:$.guard41' payload")
    silent("disc put 'guardian.ssd:$.guard42' payload")

    # --- Creating files whose names contain a wildcard character -------
    section("create")
    show("disc put 'guardian.ssd:$.guard#1' payload")
    show("disc put 'guardian.ssd:$.guard#2' payload")
    show("disc ls 'guardian.ssd:$'")

    # --- Copying the whole disc, wildcard-named files and all ----------
    section("copy")
    silent("disc create runnable.ssd --title GUARDIAN")
    show("disc cp 'guardian.ssd:$.*' 'runnable.ssd:$/'")
    show("disc ls 'runnable.ssd:$'")

    # --- Retrieving one wildcard-named file ----------------------------
    # By default guard#1 is a *pattern*: # matches any one character, so
    # it also selects guard41. Copied into a directory, both arrive.
    section("decoy")
    silent("disc create glob.ssd --title GLOB")
    show("disc cp 'runnable.ssd:$.guard#1' 'glob.ssd:$/'")
    show("disc ls 'glob.ssd:$'")

    # --no-wildcards takes the name literally, so guard#1 means exactly
    # the file with the # in it.
    section("literal")
    silent("disc create exact.ssd --title EXACT")
    show("disc cp --no-wildcards 'runnable.ssd:$.guard#1' 'exact.ssd:$.guard#1'")
    show("disc ls 'exact.ssd:$'")

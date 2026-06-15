"""Recipe for ``oaknut-basic number``.

Sections:

  pipe   Read unnumbered source from stdin, write the numbered listing
         to stdout — the bare filter form.
  files  Number a file into another file, then show the result.
  step   Number with a custom --step increment.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    section("pipe")
    show("printf 'PRINT \"HELLO\"\\nGOTO 10\\n' | oaknut-basic number")

    section("files")
    silent("printf 'CLS\\nPRINT \"HI\"\\nEND\\n' > draft.bas")
    show("oaknut-basic number draft.bas numbered.bas")
    show("cat numbered.bas")

    section("step")
    show("printf 'CLS\\nPRINT \"HI\"\\nEND\\n' | oaknut-basic number --step 5")

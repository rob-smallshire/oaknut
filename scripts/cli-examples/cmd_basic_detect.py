"""Recipe for ``oaknut-basic detect``.

Sections:

  detect  Identify tokenised BBC BASIC by structure alone. A real
          program is built first with `tokenise`; a plain-text file
          stands in for arbitrary data.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, show_error, silent  # noqa: E402

with in_tmp_dir():
    section("detect")
    silent("printf '10 PRINT \"HELLO\"\\n20 GOTO 10\\n' | oaknut-basic tokenise > PROG")
    silent("printf 'just some notes, not a program\\n' > NOTES")
    # A tokenised program is recognised; exit code 0.
    show("oaknut-basic detect PROG")
    # A non-program is rejected; exit code 1 (a shell filter would skip it).
    show_error("oaknut-basic detect NOTES", returncode=1)

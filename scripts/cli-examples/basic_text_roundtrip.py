"""Round-trip BBC BASIC between host text and a tokenised DFS program.

A BBC Micro stores a BASIC program on disc in *tokenised* form — keywords
packed to single bytes, lines framed by ``&0D`` markers — not as the
source text you type. ``oaknut-basic`` converts between the two, and it is
built to stand either side of ``disc`` in a pipe, so authoring a program
on the host and storing it ready-to-CHAIN is a single command, as is
lifting one back out to an editable text file.

Sections:

  author   The host-side source: a plain, numbered ``.bas`` text file.
  put      Tokenise the source and store it on the disc in one pipe.
  get      Read the tokenised program back out to a host text file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

# A small, numbered program authored in a modern editor (UTF-8).
_SOURCE = (
    "10 REM Greeting\n"
    "20 FOR I%=1 TO 3\n"
    '30   PRINT "HELLO WORLD"\n'
    "40 NEXT I%\n"
    "50 END\n"
)

with in_tmp_dir():
    Path("greeting.bas").write_text(_SOURCE, encoding="utf-8")
    silent("disc create greeting.ssd --title BASIC")

    section("author")
    # The source as it sits on the host — numbered text, nothing Acorn yet.
    show("cat greeting.bas")

    section("put")
    # Tokenise the text and store the program bytes in one pipe. `disc put`
    # reads stdin when no host path is given, so no trailing `-` is needed;
    # --load/--exec stamp the addresses a BASIC program carries on disc.
    show(
        "oaknut-basic tokenise --encoding utf-8 greeting.bas "
        "| disc put 'greeting.ssd:$.GREET' --load 0x1900 --exec 0x8023"
    )
    show("disc ls 'greeting.ssd:$'")

    section("get")
    # The reverse: stream the stored program through the de-tokeniser into
    # a host text file. --encoding utf-8 writes LF-terminated source an
    # ordinary editor can open, rather than the BBC `acorn` set with CRs.
    show(
        "disc cat 'greeting.ssd:$.GREET' "
        "| oaknut-basic detokenise --encoding utf-8 > recovered.bas"
    )
    show("cat recovered.bas")

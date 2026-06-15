Cookbook
========

Worked examples that use ``oaknut.basic`` directly. Each is a small,
complete program.


Tokenise a listing to a file
----------------------------

.. code-block:: python

   from pathlib import Path

   from oaknut.basic import tokenise

   source = Path("menu.bas").read_text(encoding="utf-8")
   Path("MENU").write_bytes(tokenise(source))

The source string is the program's logical text; if it contains
non-ASCII characters, encode them to the Acorn character set before
tokenising (or let the CLI's ``--encoding`` do it). See
:doc:`/api/patterns/round-tripping` for the code-point contract.


De-tokenise a stored program
----------------------------

.. code-block:: python

   from pathlib import Path

   from oaknut.basic import detokenise

   listing = detokenise(Path("MENU").read_bytes())
   print(listing)


Number unnumbered source, then tokenise
---------------------------------------

.. code-block:: python

   from oaknut.basic import number_lines, tokenise

   draft = "PRINT \"HELLO\"\nGOTO 10"

   # Two steps...
   numbered = number_lines(draft, start=10, step=10)
   program = tokenise(numbered)

   # ...or one, with auto-numbering inside tokenise.
   program = tokenise(draft, start=10, step=10)


Validate a program defensively
------------------------------

Because every codec failure is a :class:`~oaknut.basic.BASICError`, a
batch tool can convert what it can and collect the rest:

.. code-block:: python

   from oaknut.basic import detokenise, BASICError

   def to_listing(program: bytes) -> str | None:
       try:
           return detokenise(program)
       except BASICError as exc:
           log.warning("skipping malformed program: %s", exc)
           return None


Round-trip through a disc image
-------------------------------

When the program lives on a disc, the path-object wrappers compose the
codec with the disc's encoding and the right load address — prefer them
to calling :func:`tokenise` / :func:`detokenise` by hand:

.. code-block:: python

   from oaknut.dfs import DFS

   with DFS.from_file("game.ssd") as disc:
       menu = disc.root / "$" / "MENU"
       listing = menu.read_basic()
       menu.write_basic(listing.replace("GOTO 10", "GOTO 20"))

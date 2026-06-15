Auto-numbering
==============

BBC BASIC lines must be numbered. Source captured or authored without
numbers — the form you type under :term:`AUTO` — has to be numbered
before it will tokenise or run. ``oaknut-basic`` offers numbering two
ways.


The ``number`` command
----------------------

``number`` prepends an ascending line number to every line, exactly as
``AUTO start,step`` would:

.. cli-example:: cmd_basic_number
   :section: step

``--start`` sets the first line's number (default 10) and ``--step`` the
increment (default 10). Internal references such as ``GOTO`` are left
untouched, so they must already match the numbering you request — the
command does not rewrite jump targets.


Auto-numbering inside ``tokenise``
----------------------------------

Passing ``--start`` and/or ``--step`` to ``tokenise`` numbers the source
and tokenises it in one step — equivalent to typing the program into the
interpreter with ``AUTO`` switched on:

.. cli-example:: cmd_basic_tokenise
   :section: auto

The two options are identical to the ones on ``number``; supplying either
turns auto-numbering on, with the other defaulting to 10.


Already-numbered source is an error
-----------------------------------

Auto-numbering only makes sense for source that has *no* numbers. If you
ask ``tokenise`` to auto-number a listing that already carries line
numbers, it refuses rather than double-numbering — the fix is to drop
``--start`` / ``--step`` and tokenise the numbered listing directly:

.. cli-example:: cmd_basic_tokenise
   :section: already-numbered

Without auto-numbering, ``tokenise`` requires every line to begin with a
number, just like a saved ``LIST``; an unnumbered line is reported with
its position.

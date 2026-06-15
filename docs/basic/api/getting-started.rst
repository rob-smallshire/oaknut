Getting started
===============

The library is function-shaped: there is no program object to construct.
Three functions, importable straight from the ``oaknut.basic``
namespace, do the work.

.. code-block:: python

   from oaknut.basic import tokenise, detokenise, number_lines


Tokenising and de-tokenising
----------------------------

``tokenise`` takes a numbered source listing as a :class:`str` and
returns the tokenised program as :class:`bytes`; ``detokenise`` does the
reverse:

.. code-block:: python

   program = tokenise("10 PRINT \"HELLO\"\n20 GOTO 10\n")
   # program is bytes: 0x0D 0x00 0x0A ... 0x0D 0xFF

   listing = detokenise(program)
   # listing is "10 PRINT \"HELLO\"\n20 GOTO 10\n"

The two are exact inverses at the byte level — see
:doc:`/api/patterns/round-tripping` for what that guarantees, and for
the character-encoding contract the strings follow.


Numbering
---------

``number_lines`` prepends ascending line numbers to unnumbered source,
the :term:`AUTO` equivalent:

.. code-block:: python

   number_lines("PRINT\nGOTO 10", start=10, step=10)
   # "10 PRINT\n20 GOTO 10"

``tokenise`` accepts the same ``start`` and ``step`` keywords directly,
to number and tokenise unnumbered source in one call:

.. code-block:: python

   tokenise("PRINT\nEND", start=10, step=10)


On a disc image
---------------

When the program lives in a disc image, prefer the path-object wrappers
over calling the codec by hand. :meth:`oaknut.dfs.DFSPath.write_basic`
and :meth:`~oaknut.dfs.DFSPath.read_basic` (and the ADFS equivalents)
compose the codec with the correct load-address default and the disc's
character encoding:

.. code-block:: python

   from oaknut.dfs import DFS

   with DFS.from_file("game.ssd") as disc:
       (disc.root / "$" / "MENU").write_basic("10 PRINT\n20 END")
       print((disc.root / "$" / "MENU").read_basic())

Never move a BASIC program through ``read_text`` / ``write_text``: a
tokenised program is bytecode, and a text codec would mangle it.

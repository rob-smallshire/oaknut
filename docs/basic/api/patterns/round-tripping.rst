Round-tripping and code points
==============================

:func:`~oaknut.basic.tokenise` and :func:`~oaknut.basic.detokenise` are
built to be exact inverses, so a program can be taken apart and put back
together without drift. Understanding *exactly* what round-trips — and in
which representation — is the key to using them safely.


Byte-exact in both directions
-----------------------------

For any valid tokenised program, de-tokenising and re-tokenising
reproduces the original bytes:

.. doctest::

   >>> from oaknut.basic import tokenise, detokenise
   >>> program = tokenise("10 PRINT\n20 GOTO 10\n")
   >>> tokenise(detokenise(program)) == program
   True

This is the strong guarantee, and the one to lean on: compare *programs*
(bytes), not listings (text).


Source text does not always survive unchanged
----------------------------------------------

The reverse comparison — ``detokenise(tokenise(source)) == source`` — is
*not* guaranteed, because the tokeniser normalises some source forms that
have only one tokenised representation. The clearest case is keyword
:term:`abbreviation`: ``P.`` and ``PRINT`` tokenise to the same byte, so
both de-tokenise to ``PRINT``:

.. doctest::

   >>> detokenise(tokenise("10 P.")).strip()
   '10 PRINT'

A leading line number is likewise re-rendered in a canonical form. When
you need an exact comparison, tokenise both sides and compare the bytes.


Programs from a greedier tokeniser
----------------------------------

The byte-exact guarantee above assumes the program was crunched by the
BBC BASIC ROM, which :func:`~oaknut.basic.tokenise` emulates by default
(``crunch="rom"``). A class of early-1980s commercial programs was
crunched by a *greedier* third-party tool whose keyword recognition
differs from the ROM in three small ways — inside ``&`` hex constants,
across ``FN``/``PROC`` names, and in conditional-keyword suppression — so
their de-tokenised source does **not** re-tokenise to the original bytes
under the ROM default.

Passing ``crunch="greedy"`` reproduces that tool, restoring the
byte-exact round-trip for such a program:

.. doctest::

   >>> greedy = tokenise("10 A=?&FE60ANDROW%\n", crunch="greedy")
   >>> tokenise(detokenise(greedy), crunch="greedy") == greedy
   True
   >>> tokenise(detokenise(greedy)) == greedy   # the ROM default cannot
   False

Use it only when you need to regenerate such a program byte-for-byte; the
default stays ROM-accurate. The full rule differences are described in
:func:`~oaknut.basic.tokenise`.


Code-point semantics of the string
----------------------------------

The functions work in ``str`` ↔ ``bytes`` pairs, and the string side
uses **latin-1 / code-point semantics**: a character contributes the byte
``ord(c)``, and a stored byte ``b`` de-tokenises to ``chr(b)``. The text
keeps no notion of a host character set of its own — character ``&60`` is
the byte ``&60``, whether you read it as a backtick or a pound sign.

.. doctest::

   >>> tokenise("10 PRINT")[-3:]   # PRINT token, then the &0D &FF end marker
   b'\xf1\r\xff'

Mapping those code points onto a real character set — the BBC
:term:`Acorn character set`, or UTF-8 for host editing — is a separate,
caller-side concern. The CLI does it at its I/O boundary
(see :doc:`/cli/conventions/encoding`); a library caller that round-trips
through a disc image gets it from the path object's ``read_basic`` /
``write_basic`` methods. This keeps the codec itself encoding-free and,
as a result, byte-exact.

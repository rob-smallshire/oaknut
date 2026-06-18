Text encoding and line endings
==============================

A tokenised program is bytes, but its source listing is text — and that
text has to be in *some* character encoding. The ``--encoding`` option,
accepted by every ``oaknut-basic`` command, says which one, and it
governs line endings to match.


Why it defaults to ``utf-8``
----------------------------

The text side of ``number``, ``tokenise`` and ``detokenise`` is the
source you author and read in a modern editor, so all three default
``--encoding`` to ``utf-8`` and behave like ordinary text utilities: a
listing tokenises and de-tokenises with no flag at all. A ``£`` typed as
UTF-8 maps to the BBC pound sign on the way in, and an Acorn ``£`` renders
as UTF-8 on the way out.

The BBC's own 8-bit :term:`Acorn character set` is one flag away. On real
media a program's string literals and ``REM`` text are stored in it (the
pound sign is ``&60``, not ASCII's ``&23``; characters above ``&7F``
differ from Latin-1), so ``--encoding acorn`` treats the text as those raw
bytes, dropping straight onto — or coming straight off — a disc image with
no conversion.

.. note::

   The ``data`` commands default to ``acorn`` instead, because there
   ``--encoding`` names the character set of the string records *inside*
   the BBC data file, not a host text stream. Those bytes are Acorn's, so
   ``acorn`` is the faithful reading.


Choosing an encoding
--------------------

``--encoding utf-8`` (the default for ``number`` / ``tokenise`` / ``detokenise``)
   The text side is UTF-8. Use this for a listing you author or read in
   a modern editor. On ``tokenise``, UTF-8 input is decoded and the
   non-ASCII characters that have an Acorn equivalent (``£`` and friends)
   are mapped into it; on ``detokenise``, the Acorn bytes are rendered
   as UTF-8.

``--encoding acorn``
   The text side is the BBC character set, byte for byte. Use this when
   the listing must be the raw Acorn bytes — taken straight off a disc
   image, or written back to one verbatim.

Any encoding the Python runtime knows is accepted; an unknown name is a
usage error.


Line endings
-----------

The encoding also picks the line terminator of *text* output, so it
matches the platform the text is for:

- ``acorn`` writes the BBC-native carriage return (``\r``);
- every other encoding writes the host-native line feed (``\n``).

Input line endings are accepted in any of the ``\n``, ``\r`` or
``\r\n`` forms regardless of encoding, so a listing edited on any
platform tokenises cleanly. Tokenised program bytes are binary and carry
no line-ending translation at all.

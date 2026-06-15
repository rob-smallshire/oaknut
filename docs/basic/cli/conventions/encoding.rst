Text encoding and line endings
==============================

A tokenised program is bytes, but its source listing is text — and that
text has to be in *some* character encoding. The ``--encoding`` option,
accepted by every ``oaknut-basic`` command, says which one, and it
governs line endings to match.


Why it defaults to ``acorn``
----------------------------

On real media a BBC BASIC program's string literals and ``REM`` text are
stored in the BBC's 8-bit :term:`Acorn character set` (the pound sign is
``&60``, not ASCII's ``&23``; characters above ``&7F`` differ from
Latin-1). ``tokenise`` and ``detokenise`` therefore default ``--encoding``
to ``acorn``: the text they read or write is treated as the BBC character
set, so the result drops straight onto — or comes straight off — a disc
image with no further conversion.

.. note::

   The ``number`` command is plain text in, plain text out, so it
   defaults to ``utf-8`` like an ordinary text utility. ``tokenise`` and
   ``detokenise`` deal with BBC programs, so they default to ``acorn``.


Choosing an encoding
--------------------

``--encoding acorn`` (the default for ``tokenise`` / ``detokenise``)
   The text side is the BBC character set. Use this when the listing
   came from, or is going to, a BBC program — including everything piped
   to or from ``disc get`` / ``disc put``.

``--encoding utf-8``
   The text side is UTF-8. Use this for a listing you author or read in
   a modern editor. On ``tokenise``, UTF-8 input is decoded and the
   non-ASCII characters that have an Acorn equivalent (``£`` and friends)
   are mapped into it; on ``detokenise``, the Acorn bytes are rendered
   as UTF-8.

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

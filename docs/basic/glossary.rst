Glossary
========

Project-specific vocabulary, in one place so other pages can use the
terms without parenthetical re-definition. Cross-referenced from prose
with the ``:term:`` role.

.. glossary::
   :sorted:

   BBC BASIC II
      The second revision of Acorn's BASIC interpreter, shipped in the
      BBC Micro's 16 KB language ROM. ``oaknut.basic`` reproduces this
      version's tokeniser and de-tokeniser exactly. Later versions
      (BASIC IV on the Master, BASIC V on the Archimedes) keep the
      scheme but change token values; BASIC V additionally uses
      multi-byte tokens, which BBC BASIC II does not.

   tokenising
      Converting BBC BASIC source text into the compact byte form the
      interpreter stores and runs. Keywords become single-byte
      :term:`tokens <token>`, leading line numbers move into each line's
      header, and referenced line numbers are encoded with the
      :term:`line-number token`. The inverse is :term:`de-tokenising`.

   de-tokenising
      Converting a stored, tokenised program back into a source-text
      listing — what the BBC's ``LIST`` command does. Tokens expand to
      their keyword spelling and encoded line-number references decode
      back to plain decimal.

   token
      A single byte in the range ``&80``–``&FF`` standing in for a BASIC
      keyword (``&F1`` is ``PRINT``, ``&E5`` is ``GOTO``). BBC BASIC II
      has 126 keyword tokens; a handful of pseudo-variable keywords carry
      two, one for each of their function and assignment forms.

   line-number token
      The byte ``&8D``, which introduces a three-byte encoded line-number
      reference inside a program body (after ``GOTO``, ``THEN``,
      ``GOSUB``, …). The encoding lifts the value clear of ``&0D`` so a
      reference can never be mistaken for a line terminator. Not a
      keyword token: the tokeniser produces it and the de-tokeniser
      special-cases it.

   crunch
      Acorn's name for the routine that tokenises a line of input — the
      lexical pass that recognises keywords and packs the line. The
      ``oaknut.basic`` tokeniser reproduces its behaviour, including its
      start-of-statement and line-number "armed" state.

   pseudo-variable
      A keyword that is both readable and assignable — ``PAGE``,
      ``PTR``, ``TIME``, ``LOMEM``, ``HIMEM``. Each tokenises to its
      *function* form when read as a value and its *assignment* form at
      the start of a statement, so the byte differs by context.

   abbreviation
      A keyword typed as a prefix followed by ``.`` — ``P.`` for
      ``PRINT``, ``F.`` for ``FOR``. The tokeniser accepts the shortest
      prefix that resolves unambiguously in the ROM's keyword order. The
      de-tokeniser always expands abbreviations to the full keyword, so a
      round-trip through both normalises them.

   AUTO
      The BBC's automatic line-numbering mode: it prompts with an
      ascending line number before each line you type. ``oaknut-basic``
      reproduces it as the ``number`` command and the ``--start`` /
      ``--step`` options on ``tokenise``.

   Acorn character set
      The BBC Micro's 8-bit character encoding, registered by
      ``oaknut.file`` as the ``acorn`` text codec. It differs from ASCII
      mainly above ``&7F`` and in a few low positions (the pound sign is
      ``&60``). String literals and ``REM`` text in a BASIC program are
      stored in this set; the CLI's ``--encoding`` option bridges it to
      UTF-8 for host editing.

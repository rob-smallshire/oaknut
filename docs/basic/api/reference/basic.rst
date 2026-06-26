``oaknut.basic``
================

.. module:: oaknut.basic

The BBC BASIC II tokeniser, de-tokeniser, and line-numbering facade.


Conversion functions
---------------------

.. autofunction:: oaknut.basic.tokenise

.. autofunction:: oaknut.basic.detokenise

.. autofunction:: oaknut.basic.detokenise_body

.. autofunction:: oaknut.basic.number_lines


Token stream
------------

De-tokenising to text loses keyword *adjacency* — the body ``?Q <PLOT>
?Q`` renders as ``?QPLOT?Q``, which the ROM tokeniser re-reads as the
variable ``QPLOT``. A consumer that must recover the program (a faithful
front end, a re-tokeniser) needs the bytes as a token stream, not text.
:func:`~oaknut.basic.scan` provides it for an unframed line body, and
:func:`~oaknut.basic.scan_program` walks the ``&0D``-framed stored form.
The text de-tokenisers above are the join of these streams' values.

.. autofunction:: oaknut.basic.scan

.. autofunction:: oaknut.basic.scan_program

.. autoclass:: oaknut.basic.Token
   :members:

.. autoclass:: oaknut.basic.TokenKind
   :members:

.. autoclass:: oaknut.basic.LineRecord
   :members:


Dialects
--------

BBC BASIC II is the BBC Micro's 8-bit language ROM. BBC BASIC V — the
Archimedes / RISC OS ARM BASIC — keeps that token table but re-uses the
``&C6``/``&C7``/``&C8`` command bytes as two-byte *escape prefixes* (the
following byte selects an extended keyword such as ``SUM``, ``RENUMBER``,
``CASE``, ``SYS`` or ``ORIGIN``) and re-purposes several single-byte
slots (``&7F`` becomes ``OTHERWISE``; ``&C9``-``&CE`` become the block
keywords ``WHEN``/``OF``/``ENDCASE``/``ELSE``/``ENDIF``/``ENDWHILE``).
De-tokenising a BASIC V program with the BASIC II tables corrupts every
extended keyword, so :func:`~oaknut.basic.detokenise`,
:func:`~oaknut.basic.detokenise_body`, :func:`~oaknut.basic.scan` and
:func:`~oaknut.basic.scan_program` take a ``dialect`` argument.
:data:`BASIC_II` is the default everywhere.

.. autoclass:: oaknut.basic.Dialect
   :members:

.. py:data:: BASIC_II

   The default :class:`Dialect`: BBC BASIC II, the BBC Micro's 8-bit
   language ROM. No escape tokens.

.. py:data:: BASIC_V

   The :class:`Dialect` for BBC BASIC V — the Archimedes / RISC OS ARM
   BASIC — with the ``&C6``/``&C7``/``&C8`` escape tables and the
   re-purposed single-byte tokens.


Token table
-----------

The BBC BASIC II keyword/token table and flag definitions, for a
byte-level consumer that resolves tokens itself. The mapping is exposed
read-only; mutating it would corrupt the tokeniser and de-tokeniser.

.. autodata:: oaknut.basic.TOKEN_TO_KEYWORD
   :no-value:

.. autodata:: oaknut.basic.KEYWORDS
   :no-value:

.. autodata:: oaknut.basic.LINE_NUMBER_TOKEN

.. autofunction:: oaknut.basic.decode_line_number

The crunch flag bits, as read from the disassembly's bit-by-bit
dispatch:

.. autodata:: oaknut.basic.FLAG_CONDITIONAL
.. autodata:: oaknut.basic.FLAG_MIDDLE
.. autodata:: oaknut.basic.FLAG_START
.. autodata:: oaknut.basic.FLAG_FN_PROC
.. autodata:: oaknut.basic.FLAG_LINE_NUMBER
.. autodata:: oaknut.basic.FLAG_STOP_LINE
.. autodata:: oaknut.basic.FLAG_PSEUDO_VAR


Data files
----------

The channel-based files BBC BASIC creates with ``OPENOUT`` and writes
with ``PRINT#`` / ``BPUT#``. The module-level :func:`~oaknut.basic.datafile.open`
mirrors the built-in ``open``: a ``mode`` string selects a reader, a
writer, or a combined read/write object, and accepts a path or an
already-open binary stream.

.. autofunction:: oaknut.basic.datafile.open

The three classes form a diamond: a shared base carries positioning and
lifecycle, the reader and writer add their record vocabularies, and the
combined class inherits both for the update modes.

.. autoclass:: oaknut.basic.BbcBasicDataReader
   :members:

.. autoclass:: oaknut.basic.BbcBasicDataWriter
   :members:

.. autoclass:: oaknut.basic.BbcBasicDataFile
   :members:

.. autoclass:: oaknut.basic.BbcBasicDataFileBase
   :members:

A real number is stored in the BBC's packed 5-byte format. These two
functions convert between that format and a Python ``float`` in the
natural exponent-first byte order, for reuse beyond data files:

.. autofunction:: oaknut.basic.pack_float5

.. autofunction:: oaknut.basic.unpack_float5


Constants
---------

Canonical load addresses for a tokenised program on each host machine —
the addresses ``*SAVE`` uses by default:

.. autodata:: oaknut.basic.BBC_BASIC_LOAD_ADDRESS
.. autodata:: oaknut.basic.ELECTRON_BASIC_LOAD_ADDRESS

The default :term:`AUTO` numbering parameters, shared by
:func:`number_lines` and :func:`tokenise`:

.. autodata:: oaknut.basic.DEFAULT_LINE_NUMBER
.. autodata:: oaknut.basic.DEFAULT_LINE_STEP


Exceptions
----------

Every error derives from :class:`~oaknut.basic.BASICError`, itself a
:class:`oaknut.exception.DataError`. The two families mirror the two
directions; see :doc:`/api/patterns/errors` for the hierarchy and how to
catch them.

.. autoexception:: oaknut.basic.BASICError

Tokenising — source text in:

.. autoexception:: oaknut.basic.TokeniseError
.. autoexception:: oaknut.basic.UnnumberedLineError
.. autoexception:: oaknut.basic.AlreadyNumberedError
.. autoexception:: oaknut.basic.LineNumberRangeError
.. autoexception:: oaknut.basic.LineNumberOrderError
.. autoexception:: oaknut.basic.LineTooLongError

De-tokenising — token stream in:

.. autoexception:: oaknut.basic.DetokeniseError
.. autoexception:: oaknut.basic.MissingLineMarkerError
.. autoexception:: oaknut.basic.TruncatedProgramError
.. autoexception:: oaknut.basic.InvalidLineLengthError

Data files — reading and writing records:

.. autoexception:: oaknut.basic.DataFileError
.. autoexception:: oaknut.basic.UnknownTagError
.. autoexception:: oaknut.basic.DataFileTypeMismatchError
.. autoexception:: oaknut.basic.TruncatedRecordError
.. autoexception:: oaknut.basic.IntegerRangeError
.. autoexception:: oaknut.basic.StringTooLongError
.. autoexception:: oaknut.basic.Float5RangeError

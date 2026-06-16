``oaknut.basic``
================

.. module:: oaknut.basic

The BBC BASIC II tokeniser, de-tokeniser, and line-numbering facade.


Conversion functions
---------------------

.. autofunction:: oaknut.basic.tokenise

.. autofunction:: oaknut.basic.detokenise

.. autofunction:: oaknut.basic.number_lines


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

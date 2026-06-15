``oaknut.basic``
================

.. module:: oaknut.basic

The BBC BASIC II tokeniser, de-tokeniser, and line-numbering facade.


Conversion functions
---------------------

.. autofunction:: oaknut.basic.tokenise

.. autofunction:: oaknut.basic.detokenise

.. autofunction:: oaknut.basic.number_lines


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

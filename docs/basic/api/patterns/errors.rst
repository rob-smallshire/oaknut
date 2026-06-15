Error handling
==============

Every error the codec raises by intent inherits from
:class:`oaknut.basic.BASICError`, which is itself a
:class:`oaknut.exception.DataError` — part of the categorised hierarchy
every oaknut package shares. A tokeniser or de-tokeniser failure is
always a problem with the *program* (bad source, or a malformed token
stream), never a bug, so these print without a traceback at a CLI
boundary and carry ``ExitCode.DATA_ERR``.


The hierarchy
-------------

.. code-block:: text

   OaknutException                  # root (oaknut.exception)
   └── DataError                    # ExitCode.DATA_ERR (65)
       └── BASICError               # any tokeniser / de-tokeniser error
           ├── TokeniseError        # source text in
           │   ├── UnnumberedLineError
           │   ├── AlreadyNumberedError
           │   ├── LineNumberRangeError
           │   ├── LineNumberOrderError
           │   └── LineTooLongError
           └── DetokeniseError      # token stream in
               ├── MissingLineMarkerError
               ├── TruncatedProgramError
               └── InvalidLineLengthError

The two families mirror the two directions. A
:class:`~oaknut.basic.TokeniseError` is raised while turning source into
a program; a :class:`~oaknut.basic.DetokeniseError` while turning a
program back into source.


Structured attributes
----------------------

Each concrete class carries the specifics of the fault as attributes, so
a caller can build its own message or point an editor at the problem
rather than scraping the string form.

Every :class:`~oaknut.basic.TokeniseError` carries the offending source
line:

.. code-block:: python

   from oaknut.basic import tokenise, UnnumberedLineError

   try:
       tokenise("PRINT")            # no line number
   except UnnumberedLineError as exc:
       exc.line_index               # 1  (1-based line in the source)
       exc.line_text                # 'PRINT'

Some add more — :class:`~oaknut.basic.LineTooLongError` reports the
``line_number`` and the over-long ``length``;
:class:`~oaknut.basic.AlreadyNumberedError` the ``line_number`` it found.

Every :class:`~oaknut.basic.DetokeniseError` carries the byte ``offset``
into the program where the fault was found:

.. code-block:: python

   from oaknut.basic import detokenise, MissingLineMarkerError

   try:
       detokenise(b"\x99")
   except MissingLineMarkerError as exc:
       exc.offset                   # 0
       exc.found                    # 0x99  (the byte seen instead of &0D)


Actionable notes
----------------

Where a fix is obvious, the exception attaches it as a PEP 678 note, so
:func:`oaknut.exception.handled_errors` renders it under the message at a
CLI boundary. Asking to auto-number already-numbered source, for
instance, suggests dropping ``--start`` / ``--step``.


Catching errors
---------------

Catch at whatever breadth suits the call site:

.. code-block:: python

   from oaknut.basic import BASICError, TokeniseError
   from oaknut.exception import DataError

   # A specific failure you can act on.
   try:
       program = tokenise(source)
   except TokeniseError as exc:
       report_to_editor(exc.line_index, str(exc))

   # Any BASIC codec error, either direction.
   try:
       run_conversion()
   except BASICError as exc:
       log.warning("conversion failed: %s", exc)

   # Anywhere DataError is already handled uniformly, BASICError is
   # caught too — it is one.
   assert issubclass(BASICError, DataError)

Because ``BASICError`` is a ``DataError``, code that already wraps work
in :func:`oaknut.exception.handled_errors` — as the ``oaknut-basic`` CLI
does — needs no per-class mapping: the boundary reads ``exc.exit_code``
and prints the message and its notes. See
:doc:`/cli/conventions/exit-codes`.

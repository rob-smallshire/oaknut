Error handling
==============

Every error oaknut raises by intent inherits from
:class:`oaknut.exception.OaknutException` — the single root every
package shares. A small set of category subclasses sits directly
under it, and every domain-specific exception (``FSError``, the
``DFSError`` / ``ADFSError`` / ``AFSError`` trees, future package
errors) inherits from one of those categories.


The hierarchy
-------------

.. code-block:: text

   OaknutException                        # root; do not raise directly
   ├── DataError                          # ExitCode.DATA_ERR (65)
   │   └── FSError                        # shared filesystem base (oaknut.file)
   │       ├── DFSError                   # oaknut.dfs
   │       │   └── ...
   │       ├── ADFSError                  # oaknut.adfs
   │       │   └── ...
   │       └── AFSError                   # oaknut.afs
   │           └── ...
   ├── ConfigurationError                 # ExitCode.CONFIG (78)
   └── InternalError                      # ExitCode.SOFTWARE (70)

- :class:`~oaknut.exception.DataError` — the operation could not be
  satisfied with the bytes on disc or the names the caller asked for.
  Path-not-found, already-exists, disc-full, locked, malformed
  catalogue. The CLI boundary prints these without a traceback.
- :class:`~oaknut.exception.ConfigurationError` — a runtime-environment
  problem. Missing host-side resources, unwritable cache directory,
  config file referencing a missing profile. The CLI boundary prints
  these without a traceback.
- :class:`~oaknut.exception.InternalError` — something went wrong
  inside the library that we can't cleanly translate for a user. The
  CLI boundary lets these propagate with a stack trace, because that
  is the report-an-issue signal.


Exit codes live on the exception
--------------------------------

Each subclass declares its own ``ExitCode`` as a class attribute, so
the same exception classification drives both the CLI exit code and
any Python ``except`` chain you write. There is no separate mapping
table — ``exc.exit_code`` is the truth.

.. code-block:: python

   from oaknut.exception import DataError
   from oaknut.dfs.exceptions import DiscFullError

   exc = DiscFullError("no room")
   exc.exit_code           # ExitCode.CANT_CREATE
   int(exc.exit_code)      # 73
   isinstance(exc, DataError)   # True

A constructor ``exit_code=`` keyword overrides the class default for
one instance — useful when a library wants to raise a specific code
for a one-off case without inventing a private subclass:

.. code-block:: python

   from exit_codes import ExitCode
   from oaknut.file.exceptions import FSError

   raise FSError("path not found: $.MISSING", exit_code=ExitCode.OS_FILE)


Catching errors
---------------

Three idiomatic patterns:

.. code-block:: python

   from oaknut.exception import DataError, OaknutException
   from oaknut.dfs.exceptions import FileLocked

   # 1. Catch a specific failure (when you know what to do about it).
   try:
       do_dfs_thing()
   except FileLocked:
       prompt_user_for_force_flag()

   # 2. Catch the broad category (when you want a uniform UX for any
   #    "the operation was asked to do something it can't").
   try:
       do_anything()
   except DataError as exc:
       log.warning("failed: %s", exc)
       return None

   # 3. Catch every oaknut error (when crossing a process boundary).
   try:
       run_pipeline()
   except OaknutException as exc:
       send_to_error_reporting(exc)
       raise

``InternalError`` is a peer of ``DataError`` — it does **not** inherit
from it. Catching ``DataError`` only catches user / data problems;
internal errors keep their tracebacks visible.


Embedding ``handled_errors``
----------------------------

Programs that build on top of ``oaknut-disc`` (or that wrap library
calls behind their own CLI surface) can reuse the same boundary:

.. code-block:: python

   from oaknut.exception import handled_errors

   def main():
       with handled_errors():            # prints to stderr, exits with code
           run_my_pipeline()

The context manager catches :class:`DataError` and
:class:`ConfigurationError` (and any :class:`ExceptionGroup` of them),
walks each one's ``__cause__`` chain and ``__notes__``, hands the
rendered lines to a printer callback, and exits with the *first*
caught leaf's :attr:`~OaknutException.exit_code`. Pass your own
printer to customise output:

.. code-block:: python

   def shouty_printer(line, is_continuation):
       prefix = "  " if is_continuation else "!!! "
       print(f"{prefix}{line.upper()}")

   with handled_errors(shouty_printer):
       run_my_pipeline()

Pass ``debug=True`` to re-raise the caught exception after printing,
so the full Python traceback is visible — convenient during
development.

For symmetry with the CLI's `--debug` option (see
:doc:`/cli/conventions/exit-codes`), library code can read an
environment variable or its own flag to decide whether to set
``debug=True``.

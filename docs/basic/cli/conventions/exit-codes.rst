Exit codes and errors
=====================

``oaknut-basic`` reports failures the same way every oaknut CLI does:
categorised exceptions raised by the library, printed without a
traceback and turned into a conventional exit code at the command
boundary.


What can go wrong
-----------------

A tokeniser or de-tokeniser failure is always a problem with the
*program* — malformed source on the way in, or a malformed token stream
on the way out — never a bug. Every such error is a
:class:`~oaknut.exception.DataError`, so the process exits with
``ExitCode.DATA_ERR`` (``65``) and prints a one-line explanation to
standard error. For example, asking ``tokenise`` to auto-number a
listing that already has line numbers:

.. cli-example:: cmd_basic_tokenise
   :section: already-numbered

The message names the offending line (for source) or byte offset (for a
token stream), and where it helps, an actionable note follows — here,
that dropping ``--start`` / ``--step`` tokenises already-numbered source.
The exception classes behind these messages, and their attributes, are
documented under :doc:`/api/patterns/errors`.


``--debug``
-----------

A usage mistake — an unknown ``--encoding``, ``--step 0`` — is a Click
usage error and exits ``2``. For everything else, the hidden ``--debug``
flag re-raises the categorised error after printing it, so the full
Python traceback is visible:

.. code-block:: console

   $ oaknut-basic --debug tokenise broken.bas

This is for development; users see the clean message by default.


Summary
-------

================================  =====================================
Exit code                         Meaning
================================  =====================================
``0``                             Success.
``2``                             Usage error (bad option or value).
``65`` (``DATA_ERR``)             Malformed source or token stream.
================================  =====================================

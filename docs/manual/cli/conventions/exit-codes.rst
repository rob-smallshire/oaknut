Exit codes
==========

``disc`` follows the standard BSD ``sysexits.h`` exit-code vocabulary,
exposed in Python as the
`exit-codes <https://pypi.org/project/exit-codes/>`__ package's
:class:`ExitCode` enum. Using the well-known codes means scripts that
already understand ``sysexits.h`` from other tools — ``sendmail``,
``ssh``, ``rsync`` — recognise ``disc``'s codes without needing a
project-specific table.

The codes below are part of the CLI's public surface. New error
categories may map onto codes not yet listed here, but the meaning of
an existing code will not change without a major version bump.
Scripts may branch on any value listed here.


At a glance
-----------

.. list-table::
   :header-rows: 1
   :widths: 8 18 74

   * - Code
     - ``ExitCode``
     - Meaning
   * - ``0``
     - ``OK``
     - The command did what was asked.
   * - ``64``
     - ``USAGE``
     - Command-line usage error: missing argument, unknown option,
       bad option type, malformed in-image name. Emitted by Click
       before any command logic runs, or by oaknut for name-validation
       failures.
   * - ``65``
     - ``DATA_ERR``
     - Invalid data on the disc itself — a corrupted catalogue,
       inconsistent free-space map, repartition or merge structural
       conflict, or an image that does not match its claimed filing
       system. Also the fallback for any uncategorised
       :class:`~oaknut.exception.DataError`.
   * - ``70``
     - ``SOFTWARE``
     - An internal failure with no more specific category. This is
       what an :class:`~oaknut.exception.InternalError` propagates
       as when something escapes that ``disc`` was not expecting —
       and the CLI prints a Python traceback alongside it, because
       it is the report-an-issue signal.
   * - ``72``
     - ``OS_FILE``
     - A ``PATH_SPEC`` does not resolve to an entry on the disc (or
       an AFS user does not exist).
   * - ``73``
     - ``CANT_CREATE``
     - Cannot create the requested entry: name already in use, the
       parent directory is full, the partition is full, the AFS
       user's quota is exceeded, or the target directory is not
       empty (when an ``rm`` would otherwise delete it).
   * - ``74``
     - ``IO_ERR``
     - A host-side file operation failed (host permissions, host disc
       full, missing host file, AFS host-tree import error). The
       accompanying message names the host path.
   * - ``77``
     - ``NO_PERM``
     - The target file is locked (and ``--force`` was not given), or
       the current AFS user lacks the access rights for this
       operation.
   * - ``78``
     - ``CONFIG``
     - A runtime-environment / configuration problem. Not commonly
       used by ``disc`` itself (which has little user-configurable
       state) but reserved for programs built on top of the library.

Programming bugs (anything that escapes as an unhandled Python
exception) deliberately do *not* go through the catch-and-print path
— they propagate as a Python traceback to stderr, so the
report-an-issue path is obvious. A clean ``Error:`` line means the
failure is one ``disc`` knows about.


Error message format
--------------------

Every non-zero exit is accompanied by exactly one line on stderr,
prefixed with ``Error:`` and rendered in red on a colour-capable
terminal::

   $ disc cat 'image.adl:$.MISSING'
   Error: path not found: $.MISSING
   $ echo $?
   72

If the exception carries ``__notes__`` (PEP 678) or a ``__cause__``
chain, those follow as muted continuation lines underneath. Colour is
suppressed automatically when stderr is a pipe, when :envvar:`NO_COLOR`
is set, or when :envvar:`CLICOLOR` is ``0``.


``--debug``: see the traceback
------------------------------

``disc --debug <command> …`` re-raises any caught
:class:`~oaknut.exception.DataError` or
:class:`~oaknut.exception.ConfigurationError` after printing it, so
the full Python traceback appears underneath. Use it during
development or when filing a bug report; users running normal scripts
should leave it off so a single ``Error:`` line is all they see.

:class:`~oaknut.exception.InternalError` is unaffected by
``--debug``: tracebacks are always shown for it, because that *is*
the signal a user should report.


Mapping to library exceptions
-----------------------------

Every filesystem-level failure raises a subclass of
:class:`oaknut.file.FSError`, which itself inherits from
:class:`oaknut.exception.DataError`. Each subclass carries its own
:class:`ExitCode` as a class attribute, so the CLI just reads
``exc.exit_code`` and exits — no separate mapping table is needed.

The same exception type that drives the code on the CLI side is what
library callers catch on the Python side — see
:doc:`/api/patterns/errors`. The two surfaces stay consistent: if a
script and an embedded Python program both wrap the same operation,
the error classification is the same.


Composing in scripts
--------------------

The most common idiom in shell scripts is "ignore the *expected*
miss, fail loudly on anything else". Branch on the specific code:

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         # sysexits.h codes from /usr/include/sysexits.h on most Unixes;
         # exit-codes ships the same numbers.
         EX_OS_FILE=72

         if disc cat "$IMAGE":'$.!BOOT' > boot.tmp 2>/dev/null; then
             echo "has boot file"
         else
             status=$?
             case "$status" in
                 $EX_OS_FILE) echo "no boot file" ;;
                 *)           echo "disc cat failed: $status" >&2; exit "$status" ;;
             esac
         fi

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         $ErrorActionPreference = 'Continue'
         disc cat "${image}:`$.!BOOT" > boot.tmp 2> $null
         switch ($LASTEXITCODE) {
             0       { Write-Output 'has boot file' }
             72      { Write-Output 'no boot file' }
             default {
                 Write-Error "disc cat failed: $LASTEXITCODE"
                 exit $LASTEXITCODE
             }
         }

When you specifically want "tolerate this kind of miss", reach for
the per-command flag (``--force`` on ``disc rm``, ``-p`` on
``disc mkdir``, etc.) before branching on the exit code; the flag
downgrades the named class of error to a no-op while leaving
everything else loud.

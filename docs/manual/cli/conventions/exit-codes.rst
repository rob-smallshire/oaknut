Exit codes
==========

``disc`` follows a small, stable exit-code contract so it composes
naturally with shell pipelines and ``set -e`` scripting. The codes
below are part of the CLI's public surface — new ones may be added,
but the meaning of an existing code will not change without a major
version bump. Scripts may branch on any value listed here.


At a glance
-----------

.. list-table::
   :header-rows: 1
   :widths: 8 22 70

   * - Code
     - Class
     - Meaning
   * - ``0``
     - success
     - The command did what was asked.
   * - ``1``
     - generic failure
     - A filesystem-level error fired that does not have a more
       specific code yet, or something unforeseen went wrong.
   * - ``2``
     - usage error
     - Bad argument parsing — missing positional, unknown option,
       bad type. Emitted by Click before any command logic runs.
   * - ``10``
     - path not found
     - A ``PATH_SPEC`` did not resolve to anything on the disc.
   * - ``11``
     - already exists
     - Tried to create something whose name is already in use.
   * - ``12``
     - directory full
     - A flat catalogue (DFS) or hierarchical directory cannot accept
       another entry.
   * - ``13``
     - disc full
     - No free space remains in the partition.
   * - ``14``
     - locked
     - The target file is locked and ``--force`` was not given.
   * - ``15``
     - access denied
     - The current user lacks the AFS access right for this operation.
   * - ``16``
     - not empty
     - Tried to remove a directory that still has entries (use
       ``-r`` / ``--recursive``).
   * - ``20``
     - format error
     - The on-disc structure is corrupted, inconsistent, or not the
       claimed filing system.
   * - ``21``
     - invalid name
     - A supplied name violates the filing system's grammar (too
       long, illegal characters, reserved word).
   * - ``22``
     - host I/O
     - A host-side file operation failed (permissions, disk full,
       missing file). The accompanying message names the host path.
   * - ``30``
     - repartition error
     - An ``afs-init`` repartitioning step could not be completed.
   * - ``31``
     - merge conflict
     - ``afs-merge`` found a structural conflict that prevents an
       automatic merge.

Numeric ranges are conventional, not enforced: ``10``–``19`` are
filesystem-entry errors, ``20``–``29`` are structural / naming
errors, ``30``+ are higher-level workflow errors. Treat them as a
flat space when scripting.


Error message format
--------------------

Every non-zero exit is accompanied by exactly one line on stderr,
prefixed with ``Error:``::

   $ disc cat 'image.adl:$.MISSING'
   Error: path not found: $.MISSING
   $ echo $?
   10

Programming bugs (anything that escapes as an unhandled Python
exception) deliberately do *not* go through this path — they
propagate as a Python traceback to stderr with a generic exit code,
so they are loud and the report-an-issue path is obvious. A clean
``Error:`` line means the failure is one ``disc`` knows about.


Mapping to library errors
-------------------------

Every filesystem-level failure raises a subclass of
:class:`oaknut.file.FSError` from the underlying library. The CLI
catches those, maps the class to its exit code, and emits the
``Error:`` line. The same exception type that drives a code on the
CLI side is also what library callers catch on the Python side —
see :doc:`/api/patterns/errors`. The two surfaces stay consistent:
if a script and an embedded Python program both wrap the same
``disc`` invocation, the error classification is the same.


Composing in scripts
--------------------

The most common idiom in shell scripts is the "ignore the *expected*
not-found, fail loudly on anything else" pattern. Branch on the
specific code rather than swallowing all non-zero exits:

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         if disc cat "$IMAGE":'$.!BOOT' > boot.tmp 2>/dev/null; then
             echo "has boot file"
         else
             status=$?
             case "$status" in
                 10) echo "no boot file" ;;
                 *)  echo "disc cat failed: $status" >&2; exit "$status" ;;
             esac
         fi

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         $ErrorActionPreference = 'Continue'
         disc cat "${image}:`$.!BOOT" > boot.tmp 2> $null
         switch ($LASTEXITCODE) {
             0   { Write-Output 'has boot file' }
             10  { Write-Output 'no boot file' }
             default {
                 Write-Error "disc cat failed: $LASTEXITCODE"
                 exit $LASTEXITCODE
             }
         }

When you specifically want "tolerate this kind of miss", reach for
the per-command flag (``--force`` on ``disc rm``, etc.) before
branching on the exit code; the flag downgrades the named class of
error to a no-op while leaving everything else loud.

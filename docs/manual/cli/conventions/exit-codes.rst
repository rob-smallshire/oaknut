Exit codes
==========

The ``disc`` CLI follows a small, stable exit-code contract so it can
be composed with shell pipelines and ``set -e`` scripting without
surprises.

.. note::

   This page is a placeholder. Final content will cover:

   - 0 — success
   - 1 — user error (bad path, missing file, unsupported operation)
   - 2 — usage error (Click's default for bad argument parsing)
   - other codes reserved for catastrophic failure (internal bug)
   - how filesystem-level errors map onto the contract
   - relation to :class:`oaknut.file.FSError` on the Python side

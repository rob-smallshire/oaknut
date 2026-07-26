Environment variables
=====================

``disc`` reads a small, fixed set of environment variables. A command-line
flag always overrides the corresponding variable for that invocation — the
variable only sets the *default*.

oaknut's own variables
----------------------

.. envvar:: OAKNUT_DISC_RAW_ADDRESSES

   Default for the ``--raw-addresses`` flag of ``disc ls`` and ``disc stat``.
   Set it to ``1`` (or ``true`` / ``yes`` / ``on``) to show the raw load/exec
   address pair for every file instead of decoding a RISC OS filetype and
   datestamp from it. See :doc:`metadata`. Unset, or ``0``, keeps the default
   (decode when the ``&FFF`` marker is present).

Standard cross-tool variables
-----------------------------

These are widely-honoured conventions, used **unprefixed** on purpose — a tool
that renamed them would not be found by users who set them globally. They
control terminal colour on ``stderr``:

.. envvar:: NO_COLOR

   Any non-empty value disables ANSI colour, per the `NO_COLOR standard
   <https://no-color.org/>`_.

.. envvar:: CLICOLOR

   A value of ``0`` disables ANSI colour.

Colour is also suppressed automatically when ``stderr`` is not a terminal.

.. _env-naming-convention:

Naming convention
-----------------

oaknut's own variables are ``OAKNUT_<TOOL>_<SETTING>`` — upper-case,
underscore-separated, scoped to the tool that reads them (``DISC`` for the
``disc`` CLI), so a future tool can claim its own namespace without collision.
Each is wired to an explicit flag so the two stay in lock-step and a flag can
override the variable per invocation. Standard cross-tool variables such as
:envvar:`NO_COLOR` are deliberately left unprefixed.

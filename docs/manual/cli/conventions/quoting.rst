Shell quoting cheat sheet
=========================

Acorn paths use ``$``, ``.``, ``*``, and ``^`` — every one of which is
special in at least one mainstream shell. This page documents the
quoting forms that work in each shell, so other pages can show a single
canonical example and link here for the platform-specific tweaks.

.. note::

   This page is a placeholder. Final content will cover:

   - bash / zsh: ``$`` expansion in double quotes, ``*`` glob, ``^``
     in zsh ``extendedglob``
   - PowerShell: ``$`` variable expansion in double quotes, ``$`` as
     a literal in single quotes, backtick escape
   - cmd.exe: quoting limits, ``^`` escape
   - the ``*CAT`` family: Acorn star-aliases must be escaped at the
     shell level (``disc \*cat``, ``disc '*cat'``, …)
   - platform-tabbed examples for each pattern, with the host shell
     auto-selected on page load

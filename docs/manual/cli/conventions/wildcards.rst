Wildcards
=========

Several commands accept glob patterns in their in-image path argument
(``disc find``, ``disc ls`` with a pattern, ``disc rm`` with
``--recursive``, …). This page is the single source of truth for what
characters mean and how they differ per filing system.

.. note::

   This page is a placeholder. Final content will cover:

   - the supported metacharacters: ``*``, ``?``, character classes
   - case sensitivity per filing system (Acorn filenames are
     case-preserving but case-insensitive on match)
   - filename length limits (7 chars per component on DFS, 10 on ADFS,
     10 on AFS) and how they constrain useful patterns
   - escaping a literal ``*`` in a pattern
   - how this interacts with shell globbing (see :doc:`quoting`)

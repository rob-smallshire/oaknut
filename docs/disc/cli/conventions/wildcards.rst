Wildcards
=========

Some ``disc`` commands accept a glob pattern in the ``PATH_SPEC`` —
``disc find`` to locate matching paths, ``disc cp``, ``disc mv``,
``disc rm``, ``disc chmod``, ``disc lock``, ``disc unlock``,
``disc set-load``, and ``disc set-exec`` to apply an operation
across every matching entry. The pattern language is the same in
every case: Acorn wildcards, case-insensitive, anchored to a single
filename component unless an explicit recursive flag is given.


Metacharacters
--------------

.. list-table::
   :header-rows: 1

   * - Pattern
     - Matches
   * - ``*``
     - Any sequence of characters (including the empty sequence)
   * - ``#``
     - Exactly one character

Matching is case-insensitive on every supported filing system: Acorn
catalogues preserve case but compare without regard to it. ``*HELLO``,
``*Hello``, and ``*hello`` all match a file catalogued as ``HELLO``.

.. code-block:: sh

   disc find 'image.adl:*'              # every file on the disc
   disc find 'image.adl:$.Games.*'      # everything in $.Games
   disc find 'image.adl:S####'          # four chars starting with S


Anchoring and recursion
-----------------------

A pattern matches against one filename component at a time. The
literal ``.`` between components is a delimiter — patterns do not
cross it implicitly. ``$.G*`` finds every entry of ``$`` whose name
starts with ``G``; it does not match ``$.Games.Elite`` because
``Games`` and ``Elite`` are separate components.

Commands that walk into subdirectories carry an explicit ``-r`` /
``--recursive`` flag (``disc cp``, ``disc rm``, ``disc chmod``,
``disc lock``, ``disc unlock``). For wildcard-driven searches across
the whole tree, ``disc find`` traverses every directory and matches
the pattern against both the bare filename and the fully-qualified
``PATH_SPEC`` of each entry::

   disc find 'image.adl:Elite'         # any file named "Elite"
   disc find 'image.adl:$.Games.*'     # everything directly under $.Games

On a partitioned hard disc, ``disc find`` emits each result with the
partition selector that would feed back unchanged into a follow-up
command:

.. cli-example:: partition_selectors
   :section: find


Filename length matters
-----------------------

Acorn filing systems impose per-component length limits. Patterns
must produce names that fit, or the match will simply find nothing:

.. list-table::
   :header-rows: 1

   * - Filing system
     - Max filename
     - Directory naming
   * - DFS
     - 7 characters
     - Single-character directories (``$`` and ``A``..``Z``); these
       do not nest
   * - ADFS
     - 10 characters
     - Hierarchical directories, 10 characters per name
   * - AFS
     - 10 characters
     - Hierarchical directories, 10 characters per name

DFS directories do not nest. The ``$`` and ``A``..``Z`` letters that
appear before the dot are real directories in the everyday sense —
they contain files and you list them with ``disc ls`` — but a
directory cannot itself contain another directory. A pattern like
``A.M*`` finds files in the ``A`` directory whose names start with
``M``; a recursive flag has no work to do on a DFS image because
there is nothing below the top-level directories to recurse into.

Filename matching is case-insensitive, but filename *creation* is
case-preserving. ``disc cp host.txt 'image.adl:Hello'`` stores the
file as ``Hello``; subsequent ``disc ls`` will show it as ``Hello``,
and ``hello``, ``HELLO``, ``HellO`` will all find it.


Wildcards and the shell
-----------------------

Shells expand their own wildcards before ``disc`` ever sees the
arguments. A bare ``*`` on a POSIX command line will be replaced by
the matching files in the host's *current* directory, not by anything
in the disc image::

   $ ls
   bashrc  hello.txt  scsi0.dat
   $ disc find scsi0.dat:*
   #  shell expands  scsi0.dat:*  to  scsi0.dat:bashrc scsi0.dat:hello.txt
   #                                   scsi0.dat:scsi0.dat
   #  → three "image not found" errors

Quote the ``PATH_SPEC`` to keep the pattern literal::

   disc find 'scsi0.dat:*'
   disc find "scsi0.dat:*"

The same applies to ``#`` on some shells (it's a comment character
in bash and zsh when unquoted at the start of a word) and to ``$``
(parameter expansion). The full platform-by-platform breakdown lives
in :doc:`quoting`.

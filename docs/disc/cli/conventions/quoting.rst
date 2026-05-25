Shell quoting cheat sheet
=========================

Acorn paths use ``$``, ``.``, ``:``, ``*``, ``#``, ``!``, and ``^`` —
nearly every one of which is special in at least one mainstream
shell. This page documents the safe quoting form per shell so other
pages can show a canonical example and link here for the platform-
specific tweaks.

The shell tabs below auto-select based on your operating system on
first visit. You can switch tabs manually and the choice is
remembered across pages.


Characters to watch
-------------------

.. list-table::
   :header-rows: 1

   * - Character
     - Role in Acorn paths
     - Shell trouble
   * - ``$``
     - Root directory (``$.DIR.FILE``)
     - Variable / parameter expansion in bash, zsh, PowerShell
       (in double quotes)
   * - ``:``
     - ``IMAGE_SPEC:PATH_SPEC`` separator; ``adfs:`` / ``afs:`` /
       ``dfs:`` dispatch prefixes
     - Inside double quotes on PowerShell it is interpreted as a
       drive-name separator in some contexts; otherwise harmless
   * - ``.``
     - In-image component separator
     - Harmless on POSIX shells; harmless on PowerShell
   * - ``*``
     - Star-aliases (``*CAT``); wildcards (any sequence)
     - Glob expansion in bash, zsh, PowerShell, cmd
   * - ``#``
     - Wildcard (single character)
     - Start-of-line comment in bash, zsh; harmless mid-token
   * - ``!``
     - Common in file names (``!BOOT``, ``!Run``)
     - History expansion in zsh and (with ``histexpand`` on) bash;
       harmless in PowerShell
   * - ``^``
     - Parent directory
     - Pipe symbol in zsh ``extendedglob``; escape character in cmd.exe

The single safest rule is to wrap the whole ``PATH_SPEC`` (and the
``FILE_SPEC`` if you can stand it) in single quotes on POSIX shells
and single quotes on PowerShell — that suppresses expansion across
the board. The examples below use that convention.


Keep ``$``, ``!``, and ``*`` literal
------------------------------------

Acorn root-directory references (``$.PATH``), boot files (``!BOOT``),
and star-aliases (``*CAT``) all collide with shell metacharacters.

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         disc cat 'image.dat:$.!BOOT'     # single quotes: every char literal
         disc \*CAT image.dat              # backslash-escape the *
         disc '*CAT' image.dat             # or single-quote the *

   .. tab-item:: zsh
      :sync: zsh

      .. code-block:: zsh

         # zsh expands history references inside double quotes, so
         # $.!BOOT needs single quotes. Bash does the same when
         # histexpand is on (it isn't by default for non-interactive
         # bash, but it is in most interactive sessions).
         disc cat 'image.dat:$.!BOOT'
         disc '*CAT' image.dat

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         # PowerShell treats $ as a variable prefix inside double
         # quotes, so use single quotes to keep $.!BOOT literal.
         disc cat 'image.dat:$.!BOOT'
         disc '*CAT' image.dat


Wildcards: stop the shell expanding first
-----------------------------------------

Acorn wildcards (``*``, ``#``) need to reach ``disc`` intact. If you
let the shell expand them, ``disc`` sees whatever files the shell
matched in the host's *current* directory — almost never what you
meant.

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         disc find 'image.adl:$.Games.*'
         disc find 'image.adl:S####'

   .. tab-item:: zsh
      :sync: zsh

      .. code-block:: zsh

         # zsh treats # at the start of a word as a comment unless
         # interactive_comments is off — single-quote the whole arg
         # to be safe.
         disc find 'image.adl:$.Games.*'
         disc find 'image.adl:S####'

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         disc find 'image.adl:$.Games.*'
         disc find 'image.adl:S####'


Pass a single ``$.PATH`` argument
---------------------------------

When you just want one literal in-image path, the same single-quote
rule applies. The convention used throughout this manual.

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         disc ls 'image.dat:$.DIR.FILE'
         disc cat 'image.dat:$.HELLO'

   .. tab-item:: zsh
      :sync: zsh

      .. code-block:: zsh

         disc ls 'image.dat:$.DIR.FILE'
         disc cat 'image.dat:$.HELLO'

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         disc ls 'image.dat:$.DIR.FILE'
         disc cat 'image.dat:$.HELLO'


When you need double quotes
---------------------------

Double quotes are useful when part of the argument *is* a shell
variable you do want expanded — most often the image filename held
in a script variable. Mix the two quoting styles so the variable
expands and the literal part stays literal.

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         IMAGE=scsi0.dat
         disc ls "$IMAGE":'$.Library'        # $IMAGE expands, $.Library literal
         disc ls "${IMAGE}:\$.Library"       # alternative: escape the $

   .. tab-item:: zsh
      :sync: zsh

      .. code-block:: zsh

         IMAGE=scsi0.dat
         disc ls "$IMAGE":'$.Library'
         disc ls "${IMAGE}:\$.Library"

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         $image = 'scsi0.dat'
         disc ls "${image}:`$.Library"       # backtick-escape the $


Windows paths and POSIX shells
------------------------------

A Windows path written into a Bash or Zsh script needs its
backslashes escaped (or single-quoted), and the trailing
``:PATH_SPEC`` still works as written.

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         disc ls 'C:\Discs\disc.dat:$.HELLO'

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         disc ls 'C:\Discs\disc.dat:$.HELLO'

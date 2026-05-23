Shell quoting cheat sheet
=========================

Acorn paths use ``$``, ``.``, ``*``, and ``^`` — every one of which is
special in at least one mainstream shell. This page documents the
quoting forms that work in each shell, so other pages can show a
single canonical example and link here for the platform-specific
tweaks.

The shell tabs below auto-select based on your operating system on
first visit. You can switch tabs manually and the choice is
remembered.

.. note::

   This page is still being filled out — see the placeholder list
   below. The single-quotes / variable-expansion section is what was
   already documented.


Keep ``$``, ``!``, and ``*`` literal
------------------------------------

Acorn root-directory references (``$.PATH``), boot files (``!BOOT``),
and star-aliases (``*CAT``) all collide with shell metacharacters.

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         disc cat 'image.dat:$.!BOOT'     # single quotes: literal
         disc \*CAT image.dat              # backslash-escape the *

   .. tab-item:: zsh
      :sync: zsh

      .. code-block:: zsh

         # zsh expands history references inside double quotes, so $.!BOOT
         # needs single quotes. Bash does the same with histexpand on.
         disc cat 'image.dat:$.!BOOT'
         disc '*CAT' image.dat            # single-quote the *

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         # PowerShell treats $ as a variable prefix inside double quotes,
         # so use single quotes to keep $.!BOOT literal.
         disc cat 'image.dat:$.!BOOT'
         disc '*CAT' image.dat


Pass a single ``$.PATH`` argument
---------------------------------

.. tab-set::
   :sync-group: shell

   .. tab-item:: bash
      :sync: bash

      .. code-block:: bash

         disc ls 'image.dat:$.DIR.FILE'

   .. tab-item:: zsh
      :sync: zsh

      .. code-block:: zsh

         disc ls 'image.dat:$.DIR.FILE'

   .. tab-item:: PowerShell
      :sync: powershell

      .. code-block:: powershell

         disc ls 'image.dat:$.DIR.FILE'


.. note::

   Anticipated additions to this page:

   - bash / zsh: ``$`` expansion in double quotes, ``*`` glob, ``^``
     in zsh ``extendedglob``
   - PowerShell: backtick escape, ``${var}`` interpolation pitfalls
   - cmd.exe: quoting limits and ``^`` escape
   - how shell wildcards interact with the ``disc`` wildcard rules
     (see :doc:`wildcards`)

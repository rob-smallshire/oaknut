Command reference
=================

Every ``disc`` subcommand, grouped by purpose. Each entry's
arguments, options, Acorn star-aliases, and report set are live
introspections of :mod:`oaknut.disc.cli`, so the page cannot drift
from what the installed binary accepts.

The repeated report-output flags (``--no-reports``, ``--report``,
``--header``, ``--detailed``) are described once in
:doc:`/cli/conventions/output-formats` — only the format selector
``--as`` is repeated on each command below.


Inspection
----------

.. oaknut-command:: oaknut.disc.cli:ls
   :prog: disc ls

   .. cli-example:: cmd_ls

.. oaknut-command:: oaknut.disc.cli:tree
   :prog: disc tree

   .. cli-example:: cmd_tree

.. oaknut-command:: oaknut.disc.cli:stat
   :prog: disc stat

   .. cli-example:: cmd_stat

.. oaknut-command:: oaknut.disc.cli:find
   :prog: disc find

   .. cli-example:: cmd_find

.. oaknut-command:: oaknut.disc.cli:freemap
   :prog: disc freemap

   .. cli-example:: cmd_freemap

.. oaknut-command:: oaknut.disc.cli:validate
   :prog: disc validate

   .. cli-example:: cmd_validate

.. oaknut-command:: oaknut.disc.cli:cat
   :prog: disc cat

   .. cli-example:: cmd_cat

.. oaknut-command:: oaknut.disc.cli:type
   :prog: disc type

   .. cli-example:: cmd_type


File transfer (host ↔ image)
----------------------------

.. oaknut-command:: oaknut.disc.cli:get
   :prog: disc get

   .. cli-example:: cmd_get

.. oaknut-command:: oaknut.disc.cli:put
   :prog: disc put

   .. cli-example:: cmd_put

.. oaknut-command:: oaknut.disc.cli:export
   :prog: disc export

   .. cli-example:: cmd_export

.. oaknut-command:: oaknut.disc.cli:import
   :prog: disc import

   .. cli-example:: cmd_import


Modification (within an image)
------------------------------

.. oaknut-command:: oaknut.disc.cli:cp
   :prog: disc cp

   .. cli-example:: cmd_cp

.. oaknut-command:: oaknut.disc.cli:mv
   :prog: disc mv

   .. cli-example:: cmd_mv

.. oaknut-command:: oaknut.disc.cli:rm
   :prog: disc rm

   .. cli-example:: cmd_rm

.. oaknut-command:: oaknut.disc.cli:mkdir
   :prog: disc mkdir

   .. cli-example:: cmd_mkdir

.. oaknut-command:: oaknut.disc.cli:chmod
   :prog: disc chmod

   .. cli-example:: cmd_chmod

.. oaknut-command:: oaknut.disc.cli:lock
   :prog: disc lock

   .. cli-example:: cmd_lock

.. oaknut-command:: oaknut.disc.cli:unlock
   :prog: disc unlock

   .. cli-example:: cmd_unlock


Metadata
--------

.. oaknut-command:: oaknut.disc.cli:title
   :prog: disc title

   .. cli-example:: cmd_title

.. oaknut-command:: oaknut.disc.cli:opt
   :prog: disc opt

   Reading the current value:

   .. cli-example:: cmd_opt
      :section: read

   Setting numerically:

   .. cli-example:: cmd_opt
      :section: set_numeric

   Setting with a symbolic name:

   .. cli-example:: cmd_opt
      :section: set_symbolic

.. oaknut-command:: oaknut.disc.cli:get-load
   :prog: disc get-load

   .. cli-example:: cmd_get_load

.. oaknut-command:: oaknut.disc.cli:set-load
   :prog: disc set-load

   .. cli-example:: cmd_set_load

.. oaknut-command:: oaknut.disc.cli:get-exec
   :prog: disc get-exec

   .. cli-example:: cmd_get_exec

.. oaknut-command:: oaknut.disc.cli:set-exec
   :prog: disc set-exec

   .. cli-example:: cmd_set_exec


Whole-image operations
----------------------

.. oaknut-command:: oaknut.disc.cli:create
   :prog: disc create

   .. cli-example:: cmd_create

.. oaknut-command:: oaknut.disc.cli:compact
   :prog: disc compact

   .. cli-example:: cmd_compact

.. oaknut-command:: oaknut.disc.cli:expand
   :prog: disc expand

   .. cli-example:: cmd_expand


Acorn File Server (AFS)
-----------------------

.. oaknut-command:: oaknut.disc.cli:afs-plan
   :prog: disc afs-plan

   .. cli-example:: cmd_afs_plan

.. oaknut-command:: oaknut.disc.cli:afs-init
   :prog: disc afs-init

   .. cli-example:: cmd_afs_init

.. oaknut-command:: oaknut.disc.cli:afs-users
   :prog: disc afs-users

   .. cli-example:: cmd_afs_users

.. oaknut-command:: oaknut.disc.cli:afs-useradd
   :prog: disc afs-useradd

   .. cli-example:: cmd_afs_useradd

.. oaknut-command:: oaknut.disc.cli:afs-userdel
   :prog: disc afs-userdel

   .. cli-example:: cmd_afs_userdel

.. oaknut-command:: oaknut.disc.cli:afs-merge
   :prog: disc afs-merge

   .. cli-example:: cmd_afs_merge


Diagnostics
-----------

.. oaknut-command:: oaknut.disc.cli:generate-dsc
   :prog: disc generate-dsc

   .. cli-example:: cmd_generate_dsc

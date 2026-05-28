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

.. oaknut-command:: oaknut.disc.cli:for-each
   :prog: disc for-each

   .. cli-example:: cmd_for_each

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

.. oaknut-command:: oaknut.disc.cli:identify
   :prog: disc identify

   .. cli-example:: cmd_identify


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

.. oaknut-command:: oaknut.dfs.cli:expand
   :prog: disc dfs expand

   .. cli-example:: cmd_expand


AFS (Acorn Level 3 File Server)
-------------------------------

.. oaknut-command:: oaknut.afs.cli:plan
   :prog: disc afs plan

   .. cli-example:: cmd_afs_plan

.. oaknut-command:: oaknut.afs.cli:init
   :prog: disc afs init

   Passwords are set with ``--user-password NAME=VALUE``, not inside
   the ``--user`` spec: a password may contain a colon, which the
   colon-delimited spec cannot represent, so the value is split once
   on the first ``=`` and the rest taken verbatim. ``NAME`` matches a
   ``--user`` or a built-in (``Syst``, ``Boot``, ``Welcome``). No
   account has a password unless you give one — to ship a disc with
   the system account already protected, initialise with
   ``--user-password Syst=secret``.

   .. cli-example:: cmd_afs_init

.. oaknut-command:: oaknut.afs.cli:users
   :prog: disc afs users

   .. cli-example:: cmd_afs_users

.. oaknut-command:: oaknut.afs.cli:useradd
   :prog: disc afs useradd

   .. cli-example:: cmd_afs_useradd

.. oaknut-command:: oaknut.afs.cli:userdel
   :prog: disc afs userdel

   .. cli-example:: cmd_afs_userdel

.. oaknut-command:: oaknut.afs.cli:passwd
   :prog: disc afs passwd

   .. cli-example:: cmd_afs_passwd

.. oaknut-command:: oaknut.afs.cli:merge
   :prog: disc afs merge

   The recipe initialises a small source disc with an emplaced
   ``Library``, then merges its AFS tree into a separate empty
   target. The source's ``Library`` lands under the target's
   ``$`` root; the target's own freshly-created ``Passwords``
   file is left in place (it would have been excluded even if
   the source had carried one).

   .. cli-example:: cmd_afs_merge


Diagnostics
-----------

.. oaknut-command:: oaknut.adfs.cli:generate_dsc
   :prog: disc adfs generate-dsc

   .. cli-example:: cmd_generate_dsc


Filesystem identification
-------------------------

These introspect the filesystems ``disc identify`` can recognise — one
registered detector per filesystem. The set grows as filesystem
packages are installed.

.. oaknut-command:: oaknut.disc.cli:list-filesystems
   :prog: disc list-filesystems

   .. cli-example:: cmd_list_filesystems

.. oaknut-command:: oaknut.disc.cli:describe-filesystem
   :prog: disc describe-filesystem

   .. cli-example:: cmd_describe_filesystem


Meta-commands
-------------

These describe the CLI itself rather than acting on a disc image:
they introspect the reports each command produces and the output
formatters available to ``--as``. See
:doc:`../conventions/output-formats` for the concepts behind them.

.. oaknut-command:: oaknut.disc.cli:list-reports
   :prog: disc list-reports

   .. cli-example:: cmd_list_reports

.. oaknut-command:: oaknut.disc.cli:describe-report
   :prog: disc describe-report

   .. cli-example:: cmd_describe_report

.. oaknut-command:: oaknut.disc.cli:list-report-formats
   :prog: disc list-report-formats

   .. cli-example:: cmd_list_report_formats

.. oaknut-command:: oaknut.disc.cli:describe-report-format
   :prog: disc describe-report-format

   .. cli-example:: cmd_describe_report_format

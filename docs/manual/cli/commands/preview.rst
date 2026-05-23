Command reference (preview)
===========================

Side-by-side preview of the experimental ``.. oaknut-command::``
directive against the existing sphinx-click output. Two commands
shown: ``disc opt`` (multi-example, with ``@report_output``) and
``disc freemap`` (single-example, no reports).

The intent is to compare visual density and semantic structure —
definition lists with code-font terms vs. nested full-width
literal blocks — before migrating the rest of the reference page.

New rendering: ``.. oaknut-command::``
--------------------------------------

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

.. oaknut-command:: oaknut.disc.cli:freemap
   :prog: disc freemap

   .. cli-example:: cmd_freemap


Existing rendering: ``.. click::`` (sphinx-click)
-------------------------------------------------

.. click:: oaknut.disc.cli:opt
   :prog: disc opt
   :nested: none

.. click:: oaknut.disc.cli:freemap
   :prog: disc freemap
   :nested: none

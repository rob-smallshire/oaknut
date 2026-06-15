Command reference
=================

Every ``oaknut-basic`` subcommand. Each entry's arguments and options
are live introspections of :mod:`oaknut.basic.cli`, so the page cannot
drift from what the installed binary accepts.

All three commands share the same input/output model — an optional
``INPUT`` and ``OUTPUT`` defaulting to standard input and standard
output — described once in :doc:`/cli/getting-started`. The
``--encoding`` option is covered in :doc:`/cli/conventions/encoding`.


Numbering
---------

.. oaknut-command:: oaknut.basic.cli:number
   :prog: oaknut-basic number

   .. cli-example:: cmd_basic_number
      :section: step


Tokenising
----------

.. oaknut-command:: oaknut.basic.cli:tokenise
   :prog: oaknut-basic tokenise

   Numbered source in, tokenised program out:

   .. cli-example:: cmd_basic_tokenise
      :section: tokenise

   With ``--start`` / ``--step``, unnumbered source is numbered first, as
   if typed under ``AUTO``; numbered input is then an error
   (see :doc:`/cli/conventions/auto-numbering`):

   .. cli-example:: cmd_basic_tokenise
      :section: auto


De-tokenising
-------------

.. oaknut-command:: oaknut.basic.cli:detokenise
   :prog: oaknut-basic detokenise

   .. cli-example:: cmd_basic_detokenise
      :section: detokenise

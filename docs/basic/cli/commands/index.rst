Command reference
=================

Every ``oaknut-basic`` subcommand. Each entry's arguments and options
are live introspections of :mod:`oaknut.basic.cli`, so the page cannot
drift from what the installed binary accepts.

The numbering, tokenising and de-tokenising commands share the same
input/output model — an optional ``INPUT`` and ``OUTPUT`` defaulting to
standard input and standard output — described once in
:doc:`/cli/getting-started`. The ``--encoding`` option is covered in
:doc:`/cli/conventions/encoding`.


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


Data files
----------

The ``data`` subcommands read and write the type-tagged record files
BBC BASIC creates with ``OPENOUT`` and writes with ``PRINT#``. ``encode``
and ``decode`` are a lossless JSON round-trip pair; ``inspect`` shows a
file's records as a table.

.. oaknut-command:: oaknut.basic.cli:encode
   :prog: oaknut-basic data encode

   Each element of the JSON array becomes one record — a JSON integer an
   integer, a number with a fractional part a real, a string a string,
   and ``{"bytes": "hex"}`` raw bytes:

   .. cli-example:: cmd_basic_data
      :section: encode

.. oaknut-command:: oaknut.basic.cli:inspect
   :prog: oaknut-basic data inspect

   .. cli-example:: cmd_basic_data
      :section: inspect

.. oaknut-command:: oaknut.basic.cli:decode
   :prog: oaknut-basic data decode

   Reals keep their ``float`` repr (``3.5``) so they decode back to reals,
   not integers:

   .. cli-example:: cmd_basic_data
      :section: decode

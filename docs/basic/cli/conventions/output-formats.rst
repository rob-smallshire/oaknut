Output formats: ``--as``
========================

The ``data inspect`` command produces a table of records and accepts an
``--as`` flag selecting how that table is rendered.

.. code-block:: text

   --as display    pretty table, headers, Unicode glyphs
   --as tsv        tab-separated values, one row per line
   --as json       a JSON object describing the report

The ``display`` and ``tsv`` forms describe the same records; the ``json``
form additionally carries the faithful underlying values (an integer
stays a JSON integer, a real a JSON number), which makes it suitable for
scripting.


Default per output stream
-------------------------

Without ``--as``, the format is chosen from whether standard output is a
terminal:

.. list-table::
   :header-rows: 1

   * - stdout
     - Default
     - Why
   * - Terminal (interactive)
     - ``display``
     - Headers and alignment make the records legible at a glance.
   * - Pipe or redirect
     - ``tsv``
     - One row per line, stable column order, no decorative chrome, so
       ``awk``, ``cut`` and ``column -t`` get parseable input.

Override the default explicitly with ``--as`` whenever the context calls
for the other form.


Lossless round-trips use ``decode``
-----------------------------------

The ``--as json`` output of ``inspect`` is a *report* — keyed by column,
wrapped in report metadata — and is meant for reading. To move data
files in and out of JSON losslessly, use the ``decode`` and ``encode``
commands instead: their JSON is a plain array of values that ``encode``
reads back to reproduce the file byte-for-byte.

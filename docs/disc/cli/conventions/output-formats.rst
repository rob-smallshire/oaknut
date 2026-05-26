Output formats: ``--as``
========================

Every ``disc`` command that produces tabular or hierarchical output
accepts an ``--as`` flag selecting how that output is rendered.

.. code-block:: text

   --as display    pretty tables, headers, colour, Unicode glyphs
   --as tsv        tab-separated values, one row per line
   --as json       JSON object, one entry per report (see below)


Default per output stream
-------------------------

If you do not pass ``--as``, ``disc`` chooses for you based on
whether stdout is a terminal:

.. list-table::
   :header-rows: 1

   * - stdout
     - Default
     - Why
   * - Terminal (interactive)
     - ``display``
     - Headers, alignment, and styling make the output legible at a
       glance.
   * - Pipe or redirect
     - ``tsv``
     - One row per line, stable column order, no decorative chrome
       so downstream tools (``awk``, ``cut``, ``column -t``, …) get
       parseable input.

The detection happens at command start; nothing about your shell
context needs configuring. Override it explicitly with ``--as`` when
you want pretty output piped to a pager, or scriptable output to a
terminal::

   disc ls scsi0.dat | less                # pipe → tsv by default
   disc ls scsi0.dat --as display | less   # force pretty
   disc ls scsi0.dat --as json > catalog.json


The three formats in detail
---------------------------

display
~~~~~~~

The interactive format. Tables are rendered with column headers,
aligned cells, and titles; trees use box-drawing characters; key/
value reports use a labelled two-column layout. Long values are
truncated to fit the terminal width. Colour is applied where the
terminal supports it.

Reach for ``display`` when a human is reading the output. Avoid it
when scripting — the column widths and any truncation depend on
terminal size and are not part of the stable contract.

tsv
~~~

Tab-separated values, one row per line. Column headers (if not
suppressed) are emitted on the first line, prefixed with ``#`` so
``awk`` and friends can skip the line cheaply::

   $ disc ls scsi0.dat --as tsv
   #name	load	exec	length	attr
   !BOOT	4294967295	4294967295	20	WR/R
   ELITE	6400	32803	23552	LR/R
   …

Addresses and lengths are emitted as plain decimal integers — the
base is irrelevant to a consumer, so ``cut``/``awk`` get a number
they can use directly rather than a hex string to re-parse.

Field separators are literal tab characters (``\t``); no quoting,
no escaping. The column order, names, and value formats are part of
the CLI's stable contract — they will not change without a major
version bump.

Reach for ``tsv`` when feeding output into shell pipelines or other
column-aware tooling.

json
~~~~

A JSON object, with one key per report the command produced. Each
report is rendered as a list of objects (one per row) for tabular
data, or as a nested tree of objects for hierarchical data::

   $ disc stat scsi0.dat --as json
   {
     "disc": {
       "geometry": "615 cylinders, 4 heads, 32 sectors/track",
       "size": 20152320
     },
     "partition_1": { … },
     "partition_2": { … }
   }

Field names match the ``tsv`` column names. Numeric quantities —
load and exec addresses, file lengths, disc and partition sizes,
user quotas — are rendered as JSON numbers, not strings, so a
consumer can use them arithmetically without parsing. The ``display``
format shows the same values human-first (addresses as ``0x``-prefixed
hex, sizes and quotas in friendly units like ``19.2 MiB``); the
machine formats (``tsv``, ``json``) always carry the raw integer.

Reach for ``json`` when consuming output from a structured-data
tool (``jq``, ``yq``, a Python or Node script) — the structure is
the same shape your script will want.


Multi-report commands
---------------------

Some commands logically return more than one piece of information:

- ``disc stat IMAGE_SPEC`` returns a ``disc`` block (physical
  geometry + total size) and one ``partition_N`` block per
  filesystem partition (``partition_1`` for DFS or ADFS,
  ``partition_2`` for AFS on a dual-partition image).
- ``disc afs-plan`` returns several blocks (geometry, occupancy,
  suggested ``afs-init`` invocation, …).

Each sub-report has a stable name. You can ask for just the parts
you want:

.. code-block:: sh

   disc stat scsi0.dat --report partition_2          # AFS only
   disc stat scsi0.dat --report disc --report partition_1
   disc stat scsi0.dat --no-reports                  # silence display

``--report`` may be repeated; ``--no-reports`` suppresses every
report (the command's side effects still run, which matters for
action commands whose reports are incidental). ``--all-reports``
forces every report on, in case the command's default filter would
hide some.


Header control
--------------

The ``--header`` / ``--no-header`` flags toggle the leading row in
``tsv`` and the column-header row in ``display``. JSON output is
shape-stable regardless and ignores both flags. Default is
"include" — turn it off when you want a header-less stream for
``awk -F'\t'`` pipelines.


Detailed vs essential columns
-----------------------------

Some commands carry both a brief and a verbose column set —
``disc ls`` for instance can include the raw access byte alongside
the symbolic form (``--access-byte``). The ``--detailed`` /
``--essential`` flags pick between them when the command exposes
both:

- ``--essential`` — the minimum useful column set (the default for
  ``display`` and ``tsv``).
- ``--detailed`` — every column the command knows how to emit (the
  default for ``json``, since downstream scripts can simply ignore
  fields they do not need).

Either flag overrides the format-driven default.

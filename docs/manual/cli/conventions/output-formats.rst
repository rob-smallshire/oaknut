Output formats: ``--as``
========================

Every command that produces tabular or hierarchical output accepts an
``--as`` flag, implemented by `asyoulikeit
<https://github.com/sixty-north/asyoulikeit>`__. This page documents the
formats in detail so individual command pages can simply link here.

.. note::

   This page is a placeholder. Final content will cover:

   - the available formats: ``table`` (default for TTY), ``tsv``,
     ``csv``, ``json``, ``yaml``, ``html``, ``markdown``, ``tree``
   - format selection on TTY vs pipe (asyoulikeit auto-downgrades to
     a scriptable form when stdout is not a terminal)
   - multi-report output: how each command's logical sub-reports
     (``disc stat`` returns ``disc`` / ``partition_1`` / ``partition_2``,
     for example) are rendered in each format
   - which fields are stable for scripting and which are presentational
     only

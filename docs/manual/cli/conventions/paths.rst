Paths and image specifications
==============================

Every ``disc`` command that touches an image takes an ``IMAGE_SPEC`` —
the path to the host file plus, optionally, an in-image path. The two
are joined with a colon: ``image.dat:$.DIR.FILE``.

.. note::

   This page is a placeholder. Final content will cover:

   - the canonical ``IMAGE:PATH`` syntax (now the only supported form)
   - in-image path grammar per filing system: ``$.DIR.FILE`` (DFS,
     ADFS, AFS), ``^.SIBLING`` for the parent directory
   - filing-system dispatch prefixes (``afs:$``, ``adfs:$``, ``dfs:$``)
     for dual-partition images
   - auto-detection of the filing system from the image extension
     and how to override it
   - Acorn star-aliases (``*CAT``, ``*DELETE``, …) and how they map
     onto the Unix-flavoured primary verbs

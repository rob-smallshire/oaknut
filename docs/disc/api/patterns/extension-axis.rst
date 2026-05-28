The extension axis: working with any filesystem
================================================

The concrete filesystem classes — :class:`~oaknut.dfs.DFS`,
:class:`~oaknut.adfs.ADFS`, :class:`~oaknut.afs.AFS` — are the natural
choice when your code already knows which format it is reading or
writing: they expose the richest, filesystem-specific surface.

When your code does *not* know in advance — a bulk-processing script
that should work on any image you throw at it, a tool that adapts to
whichever filesystem packages happen to be installed, or anything that
mirrors what ``disc identify`` and the rest of the CLI do — work
through the **filesystem extension axis** in :mod:`oaknut.filesystem`.
The CLI itself is built on it; nothing it does is private.

The four workflows below cover almost every case. Each recipe lives in
``scripts/api-examples/`` and runs as part of the test suite, so the
code in this page is the same code the project exercises.


Identify an image by content
----------------------------

:func:`~oaknut.filesystem.identify` reports the format(s) of an image
by reading its bytes, not by trusting its extension. It returns a list
of :class:`~oaknut.filesystem.Identification` candidates ranked
best-first; each carries a :class:`~oaknut.filesystem.Confidence`, the
evidence behind the match, the partition it describes, and any nested
sub-partitions a host disc carries in ``contained``.

.. literalinclude:: ../../../../scripts/api-examples/identify_image_content.py
   :language: python
   :pyobject: report_identification

On a combined ADFS + AFS hard disc the printed tree looks like

.. code-block:: text

   STRONG   adfs
            └─ CERTAIN  afs (afs)

For an image nothing recognises, ``identify`` returns an empty list.


Open any image generically
--------------------------

Once you know what an image is, open it through the coordinator and
work against the resulting :class:`~oaknut.filesystem.Mount`. The
coordinator never imports a concrete filesystem package; it discovers
what is installed through the ``oaknut.filesystem`` entry points and
hands you a uniform interface. The same loop walks a DFS floppy, an
ADFS hard disc, an AFS partition, or a ZIP archive.

Capability protocols —
:class:`~oaknut.filesystem.AcornMetadata`,
:class:`~oaknut.filesystem.HierarchicalDirectories`,
:class:`~oaknut.filesystem.Bootable`,
:class:`~oaknut.filesystem.Titled`,
:class:`~oaknut.filesystem.FreeSpace`, and others — let the same code
opt into extra behaviour where the mount supports it and skip it
cleanly where it does not. Test for the *capability*, not the
filesystem type:

.. literalinclude:: ../../../../scripts/api-examples/open_image_generically.py
   :language: python
   :pyobject: walk_any_disc

The mount's core methods —
:meth:`~oaknut.filesystem.Mount.iter_entries`,
:meth:`~oaknut.filesystem.Mount.stat`,
:meth:`~oaknut.filesystem.Mount.read_bytes`,
:meth:`~oaknut.filesystem.Mount.exists` — have the same shape on every
filesystem. To reach a *contained* partition (the AFS tail of an ADFS
disc, say), open the nested ``Identification`` rather than the host:
its ``partition`` records the region, and
:func:`~oaknut.filesystem.region_reader` gives a windowed view to open
the contained filesystem on.


Discover what is installed
--------------------------

For tools that adapt to the environment — a chooser UI, a creation
front-end, an installer probe — enumerate the filesystems through the
coordinator. The set grows automatically as filesystem packages are
installed; no hand-wired registry.

.. literalinclude:: ../../../../scripts/api-examples/list_installed_filesystems.py
   :language: python
   :pyobject: list_installed

To examine one filesystem's full description (the same text
``disc describe-filesystem NAME`` prints), call
:func:`~oaknut.filesystem.describe_filesystem` without
``single_line``.


When to use which surface
-------------------------

.. list-table::
   :widths: 50 50
   :header-rows: 1

   * - Goal
     - Use
   * - "I'm writing a DFS-aware script."
     - :class:`oaknut.dfs.DFS`
   * - "I'm writing an ADFS-aware script."
     - :class:`oaknut.adfs.ADFS`
   * - "I have an image; I'm not sure what."
     - :func:`~oaknut.filesystem.identify`
   * - "Open this and treat it uniformly."
     - :func:`~oaknut.filesystem.create_filesystem`
   * - "Adapt to what this filesystem can do."
     - ``isinstance(mount, …)`` capability checks
   * - "What's installed in this environment?"
     - :func:`~oaknut.filesystem.filesystem_names`

The concrete-class API and the extension axis are not alternatives;
they are layers. The CLI uses the extension axis to *route* to the
right filesystem, then the concrete classes do the work underneath.
Your code can sit at whichever layer fits its job.

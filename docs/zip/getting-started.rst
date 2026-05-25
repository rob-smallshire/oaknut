Getting started
===============

Install the package into a project with ``uv``:

.. code-block:: console

   $ uv add oaknut-zip

(or ``pip install oaknut-zip`` if you are not using ``uv``).

Inspecting an archive
---------------------

The library's high-level entry points each take a path to a ``.zip``
file. ``list_archive()`` reports every member together with the Acorn
metadata recovered for it, while ``archive_info()`` summarises how that
metadata was sourced across the archive as a whole.

.. code-block:: python

   from oaknut.zip import list_archive

   for member in list_archive("NetUtils.zip"):
       print(member)

Extracting with metadata preserved
----------------------------------

``extract_archive()`` writes each member to disc and reattaches its
load/exec addresses, access bits and filetype — as extended
attributes, ``.inf`` sidecars, or filename suffixes, according to the
metadata format you ask for.

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

``archive_info()`` returns a summary dict — the member count, how many
carried each metadata source (SparkFS extras, ``.inf`` sidecars,
filename suffixes), and a filetype histogram:

.. code-block:: python

   from oaknut.zip import archive_info

   info = archive_info("NetUtils.zip")
   print(info["total"], "members;", info["sparkfs_count"], "from SparkFS extras")

Extracting with metadata preserved
----------------------------------

``extract_archive()`` writes each member to disc and reattaches its
load/exec addresses, access bits and filetype — as extended
attributes, ``.inf`` sidecars, or filename suffixes, according to the
metadata format you ask for.

.. code-block:: python

   from pathlib import Path

   from oaknut.zip import extract_archive

   extract_archive(Path("NetUtils.zip"), Path("extracted"))

That writes traditional ``.inf`` sidecars (the default). Choose a
different representation with ``meta_format`` — for example, macOS
extended attributes:

.. code-block:: python

   from oaknut.file import MetaFormat

   extract_archive(
       Path("NetUtils.zip"),
       Path("extracted"),
       meta_format=MetaFormat.XATTR_ACORN,
   )

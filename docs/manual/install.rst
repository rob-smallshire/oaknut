Installation
============

The oaknut packages provide tools for querying and manipulating Acorn
filesystem images. For interactive use and simple scripting, prefer
the Command Line Interface (CLI) tools. For lower-level programmatic
access, the Python API is likely to be more suitable. Pick the
package that names the filing system you actually need to work with
— DFS floppies, ADFS hard discs, AFS server discs, ZIP archives —
and install just that.


Prerequisites
-------------

The oaknut packages require Python 3.11 or newer.

This guide leads with `uv <https://docs.astral.sh/uv/>`__ because
that's how the project is developed and what every internal command
shows. If you do not already have ``uv``, follow Astral's
`installation guide
<https://docs.astral.sh/uv/getting-started/installation/>`__ — a
single shell command on macOS and Linux, an MSI on Windows.

``pip`` works identically with the package names below, and
`pipx <https://pipx.pypa.io/>`__ is the supported alternative if you
prefer that to ``uv``'s tool management — bootstrap it from
`its installation docs <https://pipx.pypa.io/stable/installation/>`__
if you do not already have it.


.. _cli-centric-packages:

CLI-centric packages
--------------------

These packages exist to provide a command-line tool. Installing one
gives you executables on ``PATH``.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Package
     - Commands
     - Purpose
   * - ``oaknut-disc``
     - ``disc``, ``oaknut-disc``
     - The unified disc CLI — DFS, ADFS, and AFS in one tool.
       Both command names are registered so you can use whichever you
       prefer; on a system where ``disc`` collides with another tool,
       ``oaknut-disc`` is unambiguous.
   * - ``oaknut-zip``
     - ``oaknut-zip``
     - ZIP archives carrying Acorn metadata (SparkFS extras, INF
       resolution, RISC OS filetypes). Also usable as a library — see
       below.

Most readers want ``oaknut-disc``. Pick the installation method
that matches how often you will reach for the tool — each one ends
with a concrete example invocation against an ``image.ssd``:

1. **Run once via uv, without installing.** ``uvx`` (bundled with
   ``uv``) fetches ``oaknut-disc`` into a transient cached
   environment and executes it. Subsequent invocations reuse the
   cache, so repeated runs are fast.

   .. code-block:: sh

      uvx oaknut-disc ls image.ssd

   For a persistent install that puts ``disc`` on your shell ``PATH``,
   use ``uv tool install oaknut-disc`` once, then ``disc ls image.ssd``
   from any shell thereafter.

2. **Add to a uv-managed Python project.** Use this when your project
   drives ``disc`` from a script you are writing, or when you want to
   import the library modules alongside.

   .. code-block:: sh

      uv add oaknut-disc
      uv run disc ls image.ssd

3. **Install into a pip-managed virtualenv.** The traditional path
   when ``uv`` is not part of your toolchain — install into your
   currently active venv.

   .. code-block:: sh

      pip install oaknut-disc
      oaknut-disc ls image.ssd

4. **Run once via pipx, without installing.** The pipx-side equivalent
   of ``uvx`` if you already use pipx for managing Python tools.

   .. code-block:: sh

      pipx run oaknut-disc ls image.ssd

   For a persistent install via pipx, use ``pipx install oaknut-disc``
   once, then ``disc ls image.ssd``.


.. _library-packages:

Library packages
----------------

These packages exist to be imported by your Python code.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Install
     - When you want to…
   * - ``oaknut-dfs``
     - Read or write Acorn DFS floppy images (SSD/DSD), including
       Watford DDFS and Opus DDOS variants.
   * - ``oaknut-adfs``
     - Read or write ADFS floppy or hard-disc images — Archimedes,
       RISC OS, BBC Master.
   * - ``oaknut-afs``
     - Read or write the Acorn Level 3 File Server's private on-disc
       format. Sits on top of ``oaknut-adfs``.
   * - ``oaknut-zip``
     - Read or write ZIP archives that carry Acorn metadata. Includes
       the ``oaknut-zip`` CLI as a bonus.
   * - ``oaknut-basic``
     - The BBC BASIC tokeniser and detokeniser, on its own — when you
       want to work with ``.bas`` / ``.bbc`` files outside a disc
       image.

Pick the package that names what you actually want to do. The
shared infrastructure (``oaknut-file``, ``oaknut-exception``,
``oaknut-discimage``) is pulled in automatically as a transitive
dependency — you do not normally install it directly.

.. code-block:: sh

   uv add oaknut-dfs                      # DFS floppies
   uv add oaknut-adfs                     # ADFS floppies + hard discs
   uv add oaknut-afs                      # AFS server discs (also pulls oaknut-adfs)

A program that walks every filesystem family installs the relevant
top-level packages and imports from each:

.. code-block:: python

   from oaknut.dfs import DFS
   from oaknut.adfs import ADFS
   from oaknut.afs import AFS
   from oaknut.zip import extract_archive


The ``oaknut`` placeholder
--------------------------

There is a distribution called simply ``oaknut`` on PyPI. **It is a
namespace placeholder** — it has no runtime code and no dependencies,
and it exists only to own the name so that the namespace structure
across all the ``oaknut-*`` packages stays coherent.

.. code-block:: sh

   pip install oaknut          # succeeds, installs nothing useful

If you typed that hoping to "install everything", install the
specific ``oaknut-*`` package(s) you want instead — see
:ref:`cli-centric-packages` and :ref:`library-packages`.


Verifying the install
---------------------

For the CLI:

.. code-block:: sh

   disc --version

For the Python API, any installed package answers to ``__version__``:

.. code-block:: python

   >>> import oaknut.dfs
   >>> oaknut.dfs.__version__
   '10.7.0'


Where to go next
----------------

- CLI users: continue with :doc:`cli/getting-started` for a guided
  walk-through, then :doc:`cli/cookbook` for composed recipes.
- Library users: jump into :doc:`api/cookbook` for worked examples,
  with :doc:`api/patterns/index` for the cross-cutting concepts every
  package shares.

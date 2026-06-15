Installation
============

``oaknut-basic`` provides both a command-line tool for converting BBC
BASIC programs and a Python library that embeds the same codec. Install
it on its own to work with ``.bas`` / ``.bbc`` files outside a disc
image; it is also pulled in automatically by ``oaknut-dfs`` and
``oaknut-adfs`` to back their ``read_basic`` / ``write_basic`` methods.


Prerequisites
-------------

``oaknut-basic`` requires Python 3.11 or newer.

This guide leads with `uv <https://docs.astral.sh/uv/>`__ because that's
how the project is developed and what every internal command shows. If
you do not already have ``uv``, follow Astral's `installation guide
<https://docs.astral.sh/uv/getting-started/installation/>`__. ``pip``
works identically with the same package name, and
`pipx <https://pipx.pypa.io/>`__ is the supported alternative for tool
management.


The command-line tool
---------------------

Installing the ``[cli]`` extra puts an ``oaknut-basic`` executable on
``PATH``:

.. code-block:: sh

   uv tool install "oaknut-basic[cli]"
   oaknut-basic --help

Or run it once, without installing, via ``uvx``:

.. code-block:: sh

   uvx --from "oaknut-basic[cli]" oaknut-basic number menu.bas

The bare ``oaknut-basic`` distribution (no extra) is the importable
library only; the CLI's Click and rendering dependencies arrive with the
``[cli]`` extra so a program that just imports the codec stays lean.


The library
-----------

For programmatic use, add the package to your project:

.. code-block:: sh

   uv add oaknut-basic

…or with ``pip`` into the active virtualenv:

.. code-block:: sh

   pip install oaknut-basic

A first program — tokenise a listing and write it as a ``.bbc`` file:

.. code-block:: python

   from pathlib import Path

   from oaknut.basic import tokenise

   source = "10 PRINT \"HELLO\"\n20 GOTO 10\n"
   Path("HELLO.bbc").write_bytes(tokenise(source))


Where to go next
----------------

- CLI users: continue with :doc:`cli/getting-started`, then
  :doc:`cli/cookbook` for composed recipes.
- Library users: jump into :doc:`api/getting-started`, with
  :doc:`api/patterns/index` for the cross-cutting concepts.

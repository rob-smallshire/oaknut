Getting started
===============

The ``oaknut-basic`` command-line tool converts BBC BASIC programs
between text and their tokenised on-disc form, and numbers unnumbered
source. It is built to sit in a Unix pipeline, so it composes naturally
with ``disc get`` and ``disc put`` from the :doc:`disc manual
</index>`.

Install the tool with its ``[cli]`` extra (see :doc:`/install`), then
ask it what it can do:

.. code-block:: console

   $ oaknut-basic --help

Three subcommands
-----------------

``number``
   Prepend ascending line numbers to source that has none — the
   :term:`AUTO` equivalent. See :doc:`/cli/conventions/auto-numbering`.

``tokenise``
   Turn a numbered listing into a stored, tokenised program.

``detokenise``
   Turn a stored program back into a listing.

Every subcommand reads from a file or standard input and writes to a
file or standard output, so the same invocation works file-to-file and
in a pipe.

Files and pipes
---------------

Each command takes an optional ``INPUT`` and ``OUTPUT`` argument. Both
default to ``-`` — standard input and standard output — so a bare
command is a filter:

.. cli-example:: cmd_basic_number
   :section: pipe

Naming the files instead converts one to the other on disc:

.. cli-example:: cmd_basic_number
   :section: files

Round-tripping
--------------

Tokenising and de-tokenising are exact inverses at the byte level, so a
program survives a there-and-back trip unchanged:

.. cli-example:: cmd_basic_tokenise
   :section: roundtrip

Composing with ``disc``
-----------------------

Because every command is a stdio filter, it slots between ``disc get``
and ``disc put`` to edit a program in place on a disc image — pull the
tokenised program out, de-tokenise it, and (after editing) tokenise it
back:

.. code-block:: console

   $ disc get game.ssd MENU - | oaknut-basic detokenise > menu.bas
   $ oaknut-basic tokenise menu.bas | disc put game.ssd MENU -

Text encoding is handled at this boundary: by default the tool reads and
writes the BBC :term:`Acorn character set`, the form a program has on
real media. Pass ``--encoding utf-8`` when the host file is UTF-8. See
:doc:`/cli/conventions/encoding`.

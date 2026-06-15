oaknut-basic
============

Convert BBC BASIC programs between their compact on-disc *tokenised*
form and a plain-text listing — the two directions a real BBC Micro
performs when you ``LOAD`` a program and ``LIST`` it.

A tokenised program is bytecode, not text: keywords like ``PRINT`` and
``GOTO`` are single bytes, line numbers are packed into the line header,
and references such as ``GOTO 100`` are scrambled into a three-byte form
that can never be mistaken for a line terminator. ``oaknut.basic``
reproduces the **BBC BASIC II** ROM's tokeniser and de-tokeniser exactly,
so a program round-trips byte-for-byte.

Alongside the codec it offers line **numbering** — prepending ascending
line numbers to source typed without them, as the BBC's ``AUTO`` command
would.

If you have not installed anything yet, start with the :doc:`install`
guide. Most readers reach for the ``oaknut-basic`` :doc:`command-line
interface <cli/getting-started>` to convert ``.bas`` files from a shell;
the :doc:`Python API <api/getting-started>` is for programs that embed
the codec directly.

.. toctree::
   :hidden:
   :caption: Installation

   install

.. toctree::
   :hidden:
   :caption: Command-line interface

   cli/getting-started
   cli/cookbook
   cli/conventions/index
   cli/commands/index

.. toctree::
   :hidden:
   :caption: Python API

   api/getting-started
   api/cookbook
   api/patterns/index
   api/reference/index

.. toctree::
   :hidden:
   :caption: Reference

   glossary
   changelog

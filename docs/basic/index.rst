oaknut-basic
============

Work with the persistent artefacts a BBC BASIC program leaves behind —
both the **code** and the **data**.

A tokenised program is bytecode, not text: keywords like ``PRINT`` and
``GOTO`` are single bytes, line numbers are packed into the line header,
and references such as ``GOTO 100`` are scrambled into a three-byte form
that can never be mistaken for a line terminator. ``oaknut.basic``
converts a program between that form and a plain-text listing — the two
directions a real BBC Micro performs when you ``LOAD`` and ``LIST`` it —
and offers line **numbering**, prepending ascending line numbers to
source typed without them, as the BBC's ``AUTO`` command would.

A data file is just as private to the language: ``PRINT#`` writes a type
tag and the value's bytes **in reverse**, with reals in the BBC's packed
5-byte floating-point format, meant to be read back only by ``INPUT#``.
The :doc:`data-file API <api/reference/basic>` presents such a file as a
context-managed, file-like object that translates its records to and from
native Python values.

The **BBC BASIC II** ROM's behaviour is reproduced exactly throughout, so
a program round-trips between bytes and text byte-for-byte, and a data
file round-trips through Python values byte-for-byte.

If you have not installed anything yet, start with the :doc:`install`
guide. Most readers reach for the ``oaknut-basic`` :doc:`command-line
interface <cli/getting-started>` from a shell; the :doc:`Python API
<api/getting-started>` is for programs that embed the library directly.

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

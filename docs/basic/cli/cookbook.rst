Cookbook
========

Composed recipes that chain ``oaknut-basic`` with the shell and with
``disc``. Each is a pipeline you can paste and adapt.


Edit a program living on a disc image
-------------------------------------

Pull the tokenised program out of an image, de-tokenise it to a text
file, edit it, then tokenise it back in place:

.. code-block:: console

   $ disc get game.ssd MENU - | oaknut-basic detokenise > menu.bas
   $ $EDITOR menu.bas
   $ oaknut-basic tokenise menu.bas | disc put game.ssd MENU -

``disc get … -`` writes the raw bytes to standard output and
``disc put … -`` reads them from standard input, so no temporary copy
of the *tokenised* form is ever needed.


Number, then tokenise, hand-typed source
----------------------------------------

Source typed without line numbers can be numbered and tokenised in one
pipeline — or in a single ``tokenise`` invocation with auto-numbering:

.. code-block:: console

   $ oaknut-basic number draft.bas | oaknut-basic tokenise > PROG
   $ oaknut-basic tokenise --start 10 --step 10 draft.bas > PROG   # equivalent


Convert a UTF-8 listing to a BBC program
----------------------------------------

A listing authored in a modern editor is UTF-8; the program on the
image must be in the Acorn character set. ``--encoding`` bridges the two
— decode the input as UTF-8 on the way in, and the tokenised output is
Acorn-native:

.. code-block:: console

   $ oaknut-basic tokenise --encoding utf-8 menu.bas | disc put game.ssd MENU -


Batch-detokenise every program on a disc
----------------------------------------

List a disc's files, pull each one out and de-tokenise it to a local
``.bas`` next to its Acorn name:

.. code-block:: console

   $ for name in $(disc ls game.ssd:$ --as tsv | cut -f1); do
   >   disc get "game.ssd:$.$name" - | oaknut-basic detokenise > "$name.bas"
   > done


Inspect a program without leaving the shell
-------------------------------------------

De-tokenise straight to the pager to read a stored program as a listing:

.. code-block:: console

   $ disc get game.ssd MENU - | oaknut-basic detokenise | less

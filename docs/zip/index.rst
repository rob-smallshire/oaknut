oaknut-zip
==========

Read ZIP archives that carry Acorn file metadata — the load and
execution addresses, access bits, and RISC OS filetypes that ordinary
unzip tools silently discard.

``oaknut.zip`` recovers that metadata from three sources, in order of
authority:

#. **SparkFS** ``ARC0`` **extra fields** embedded in the archive's own
   structure — the most reliable source.
#. **Bundled** ``.inf`` **sidecars** — both the traditional
   ``filename load exec length [access]`` form and the PiEconetBridge
   ``owner load exec perm [homeof]`` form.
#. **Unix filename suffixes** such as ``,xxx`` (filetype) or
   ``,llllllll,eeeeeeee`` (load/exec).

Where several sources describe the same member, the higher-authority
one wins.

.. toctree::
   :hidden:
   :caption: Getting started

   getting-started

.. toctree::
   :hidden:
   :caption: Reference

   reference

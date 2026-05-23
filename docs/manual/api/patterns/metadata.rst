File metadata
=============

Acorn files carry side-channel metadata — load address, exec address,
access bits, filetype — that needs preserving when files cross the
boundary between an in-image filesystem and the host filesystem.
:mod:`oaknut.file` provides the canonical types and conversions.

.. note::

   This page is a placeholder. Final content will cover:

   - :class:`oaknut.file.AcornMeta`, :class:`oaknut.file.Access`,
     :class:`oaknut.file.BootOption`
   - sidecar formats: INF (traditional and PiEconetBridge variants)
   - xattr namespaces: ``user.acorn.*`` and ``user.pieb.*``
   - filename-suffix metadata: ``,XXX`` (RISC OS) and ``-XXX`` (MOS)
   - :func:`oaknut.file.import_with_metadata` and
     :func:`oaknut.file.export_with_metadata` round-trip helpers

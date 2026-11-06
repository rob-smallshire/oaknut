``oaknut.romfs``
================

The Acorn ROM Filing System: files stored in a paged ROM (a sideways ROM
or cartridge) for the BBC Micro and Acorn Electron. A ROMFS image holds
files in Cassette Filing System block format behind a standard paged-ROM
header, so the filing system is flat: no directories, and each file
carries load and execution addresses and a lock bit. A game spread over
several ROMs is a :class:`~oaknut.romfs.ROMFSSet`.

Every name documented here is importable directly from ``oaknut.romfs``.


The filesystem
--------------

.. autoclass:: oaknut.romfs.ROMFS
   :members:

.. autoclass:: oaknut.romfs.ROMFSFile
   :members:

.. autoclass:: oaknut.romfs.ROMFSFragment
   :members:

.. autoclass:: oaknut.romfs.ROMFSSet
   :members:

The ROMFS access convention maps a file's CFS flag byte to and from the
:class:`~oaknut.file.Access` word (see :class:`~oaknut.file.AccessConvention`).

.. autoclass:: oaknut.romfs.AcornROMFSAccessConvention

.. autodata:: oaknut.romfs.ACORN_ROMFS_ACCESS


Block CRCs
----------

.. autofunction:: oaknut.romfs.crc16_ccitt


Exceptions
----------

.. autoexception:: oaknut.romfs.ROMFSError

.. autoexception:: oaknut.romfs.NotAROMFSError

.. autoexception:: oaknut.romfs.CRCError

.. autoexception:: oaknut.romfs.TruncatedROMError

.. autoexception:: oaknut.romfs.ROMFullError

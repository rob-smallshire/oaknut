CLI cookbook
============

Recipes that compose ``disc`` with shell scripting to solve real
end-to-end tasks. Each recipe is platform-tabbed (``bash`` / ``zsh`` /
``powershell``) where the syntax differs; the active tab follows the
reader's host platform on first visit.

.. note::

   The two recipes below are starter content carried over from the
   previous documentation. Anticipated further recipes:

   - bulk-export a DFS floppy to a host directory tree
   - mass-rename files using shell patterns
   - import an entire host directory into a fresh AFS server disc
   - inspect a damaged disc's catalogue without writing
   - automate WFSINIT analogues for many discs in one run


Cross-image copy
----------------

``disc cp`` takes two ``FILE_SPEC`` arguments (see :doc:`conventions/paths`).
Cross-image is the normal case; for an in-image copy, name the same
image on both sides.

.. code-block:: sh

   # Between two images.
   disc cp source.ssd:'$.HELLO' target.dat:'$.HELLO'

   # Within one image.
   disc cp image.adl:'$.Original' image.adl:'$.Copy'

Load and exec addresses are preserved. Access attributes are mapped
as losslessly as the target format allows (e.g. DFS only has a
locked bit, so public-read from ADFS is dropped).


Creating a Level 3 File Server disc
-----------------------------------

A complete walkthrough for building a bootable L3FS hard disc image:

.. code-block:: sh

   # Create a 10 MiB ADFS hard disc image
   disc create scsi0.dat --format adfs-hard --capacity 10MiB --title Server

   # Copy the file server binary from its DFS floppy
   disc cp FS3v126.ssd:'$.FS3v126' scsi0.dat:'$.FS3v126'

   # Create a !BOOT file and set the boot option
   printf '*RUN $.FS3v126\r' | disc put 'scsi0.dat:$.!BOOT' -
   disc opt scsi0.dat 3

   # Plan the AFS partition (shows geometry, free space, suggested command)
   disc afs-plan scsi0.dat

   # Initialise AFS with users and libraries
   disc afs-init scsi0.dat --disc-name Server --cylinders 309 \
     --user Syst:S --user RJS:2MiB \
     --emplace Library --emplace Library1

   # Inspect the result
   disc tree scsi0.dat

The ``--emplace`` option accepts either a shipped library name
(``Library``, ``Library1``, ``ArthurLib``) or a path to any ADFS
``.adl`` image. Everything in the image is copied into a directory
of the same name on the AFS partition.
